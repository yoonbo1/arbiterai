"""LangGraph pipelines. Two graphs share one state schema:

  ingest:  load -> route_pages -> extract(text|ocr|vlm) -> deidentify -> annotate -> chunk_embed -> audit
  query:   deidentify_q -> retrieve -> generate(small) -> validate -> [escalate(large) -> validate] -> reidentify -> audit

Invariant enforced in code: nothing leaves this process to a model endpoint unless
state["deidentified"] is True.  Tenant id is set in the first node and never changes.

Escalation: a draft that fails validation is regenerated at most MAX_ESCALATIONS (= 1) times, on
the large tier, unless it leaked PHI or the large tier resolves to the same (endpoint, model) as
the small tier (llm.tiers_identical(); SMALL_MODEL_URL/SMALL_MODEL and LARGE_MODEL_URL/LARGE_MODEL,
the latter falling back to the former when unset). A skipped escalation is recorded as
validation["escalation_skipped"] and the query fails at one attempt.

Audit: a delivered answer writes job.query.completed; anything else writes job.query.rejected
with the reasons in detail (query_outcome). Ingest writes job.ingest.completed via store.audit.

Graphs are compiled by worker.main with the checkpointer chosen by CHECKPOINTER
(default none). State holds pre-de-identification text and the plaintext phi_map, so a
persistent checkpointer must not be used with real data until that state is protected.
"""
from __future__ import annotations

import os, time
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph
from psycopg.types.json import Jsonb

from . import annotate, deid, extract, llm, reid, retrieval, store

MAX_ESCALATIONS = 1                          # large-tier retries after the small-tier draft
MAX_GENERATIONS = 1 + MAX_ESCALATIONS        # generate() may run this many times per query
ESCALATION_SKIPPED_IDENTICAL_TIERS = "large tier identical to small tier"
QUERY_COMPLETED, QUERY_REJECTED = "job.query.completed", "job.query.rejected"


class EscalationLimitExceeded(RuntimeError):
    """generate() was asked for more generations than MAX_GENERATIONS allows."""


class State(TypedDict, total=False):
    # identity — set once by the worker, never by a client
    job_id: str
    tenant_id: str
    api_key_id: str
    patient_id: str
    kind: Literal["ingest", "query"]
    # ingest
    storage_uri: str
    doc_type: str | None
    document_id: str
    pages: list[extract.Page]
    raw_text: list[str]
    facts: list[list[annotate.Fact]]   # per page, de-identified spans only
    # query
    question: str
    question_deid: str
    max_chunks: int
    chunks: list[dict]
    token_index: dict[str, tuple[str, str]]   # unified token -> (question | document_id, original)
    answer_deid: str
    answer: str
    # shared
    deidentified: bool
    phi_map: dict[str, str]          # token -> original value (encrypted before persistence)
    attempts: int
    validation: dict
    usage: dict                       # token accounting per model tier
    errors: list[str]


# ---------------------------------------------------------------- ingest nodes
def load(state: State) -> State:
    pages = extract.load_pages(state["storage_uri"])
    if not pages:
        raise ValueError("document has no pages")
    return {"pages": pages, "deidentified": False, "attempts": 0, "usage": {}, "errors": []}


def route_pages(state: State) -> State:
    """Cheap heuristic: native text layer -> 'text'; scan with clean OCR -> 'ocr';
    forms/tables/handwriting or low OCR confidence -> 'vlm' (or 'ocr' with vlm_wanted set
    when no VLM is configured). Keeps VLM to ~20-30% of pages."""
    pages = state["pages"]
    for p in pages:
        p.route = extract.choose_route(p)
    return {"pages": pages}


def extract_pages(state: State) -> State:
    texts, usage = [], dict(state.get("usage", {}))
    for p in state["pages"]:
        if p.route == "text":
            texts.append(p.native_text)
        elif p.route == "ocr":
            texts.append(extract.ocr(p))
        elif p.route == "vlm":
            t, u = extract.vlm(p)           # VLM runs locally; page images never leave the box
            texts.append(t)
            usage["large"] = usage.get("large", 0) + u
        else:
            raise ValueError(f"unknown route {p.route!r}")
    return {"raw_text": texts, "usage": usage}


def deidentify(state: State) -> State:
    # Per-page scrub with shared token state: page count is preserved by construction, so
    # store.index_document's zip(pages, texts) can never misalign.
    clean, phi_map = deid.scrub_pages(state["raw_text"])
    assert len(clean) == len(state["pages"]), "de-identified page count mismatch"
    return {"raw_text": clean, "phi_map": phi_map, "deidentified": True}


def annotate_pages(state: State) -> State:
    """Structured clinical facts from the de-identified pages (worker/annotate.py). ANNOTATE=0
    short-circuits to empty lists so the rest of the pipeline keeps working without the models."""
    assert state["deidentified"], "refusing to annotate non-de-identified text"
    if (os.environ.get("ANNOTATE") or "1").strip() != "1":
        return {"facts": [[] for _ in state["raw_text"]]}
    usage = dict(state.get("usage", {}))
    t0 = time.time()
    facts = annotate.annotate_pages(state["raw_text"], usage=usage)
    n_pages = max(1, len(facts))
    print(f"[worker] annotate {state['job_id']}: {len(facts)} page(s), {sum(len(f) for f in facts)} facts, "
          f"{(time.time() - t0) * 1000 / n_pages:.0f} ms/page", flush=True)       # counts only, never text
    return {"facts": facts, "usage": usage}


def chunk_embed(state: State) -> State:
    assert state["deidentified"], "refusing to embed non-de-identified text"
    facts = state.get("facts") or [[] for _ in state["pages"]]
    n = store.index_document(
        tenant_id=state["tenant_id"], patient_id=state["patient_id"],
        document_id=state["document_id"], pages=state["pages"], texts=state["raw_text"],
        phi_map=state["phi_map"], facts=facts,
    )
    return {"validation": {"chunks_indexed": n, "pages": len(state["pages"]),
                           "vlm_wanted_pages": sum(1 for p in state["pages"] if p.vlm_wanted),
                           "facts": annotate.counts_by_kind(facts),
                           "facts_total": sum(len(f) for f in facts)}}


# ----------------------------------------------------------------- query nodes
def deidentify_question(state: State) -> State:
    clean, phi_map = deid.scrub(state["question"])
    return {"question_deid": clean, "phi_map": phi_map, "deidentified": True,
            "attempts": 0, "usage": {}, "errors": [], "chunks": []}


def retrieve(state: State) -> State:
    chunks = retrieval.hybrid(
        tenant_id=state["tenant_id"], patient_id=state["patient_id"],   # hard filters, always
        query=state["question_deid"], k=state.get("max_chunks", 6),
    )
    # One token namespace per query: each document numbers its own placeholders from 1, so
    # without this the same label could mean different people inside one prompt.
    chunks, index = reid.unify(state.get("phi_map", {}), chunks)
    return {"chunks": chunks, "token_index": index}


def after_retrieve(state: State) -> Literal["generate", "no_chunks"]:
    return "generate" if state.get("chunks") else "no_chunks"


def generate(state: State) -> State:
    assert state["deidentified"]
    attempts = state.get("attempts", 0)
    if attempts >= MAX_GENERATIONS:          # hard stop: the routing in after_validate is not the only guard
        raise EscalationLimitExceeded(f"{attempts} generations already made (limit {MAX_GENERATIONS})")
    tier = "large" if attempts > 0 else "small"
    answer, used = llm.answer(tier, state["question_deid"], state["chunks"])
    usage = dict(state["usage"]); usage[tier] = usage.get(tier, 0) + used
    return {"answer_deid": answer, "usage": usage, "attempts": attempts + 1}


def validate(state: State) -> State:
    """Reject answers that leak PHI, cite nothing, or have low grounding. Also decides whether a
    failed draft is worth escalating: not when the large tier is the small tier."""
    v = {
        "phi_leak": deid.contains_phi(state["answer_deid"]),
        "cites_chunks": any(f"[{c['id']}]" in state["answer_deid"] for c in state["chunks"]),
    }
    score, used = llm.faithfulness_score(state["answer_deid"], state["chunks"])
    usage = dict(state.get("usage", {}))
    usage["small"] = usage.get("small", 0) + used      # judge calls are metered too
    v["faithfulness"] = score
    v["grounded"] = score >= 0.7
    v["attempts"] = state.get("attempts", 0)
    v["escalated"] = v["attempts"] > 1                   # this draft came from the large tier
    v["ok"] = (not v["phi_leak"]) and v["cites_chunks"] and v["grounded"]
    if _retry_wanted(v) and llm.tiers_identical():
        # Same model at temperature 0: a rerun cannot change the verdict and is metered at the
        # large-tier rate. Fail now, at one attempt, so the eval does not count an escalation.
        v["escalation_skipped"] = ESCALATION_SKIPPED_IDENTICAL_TIERS
    return {"validation": v, "usage": usage}


def _retry_wanted(v: dict) -> bool:
    """A failed draft deserves another generation unless it leaked PHI (never retried, so the
    leak is not reproduced) or the escalation budget is spent."""
    return (not v["ok"]) and (not v["phi_leak"]) and v["attempts"] < MAX_GENERATIONS


def may_escalate(state: State) -> bool:
    """The one routing decision for escalation: a retry is wanted and the large tier differs."""
    return _retry_wanted(state["validation"]) and not state["validation"].get("escalation_skipped")


def after_validate(state: State) -> Literal["reidentify", "generate", "fail"]:
    if state["validation"]["ok"]:
        return "reidentify"
    return "generate" if may_escalate(state) else "fail"


def reidentify(state: State) -> State:
    """Last step, only for the authorized caller, only the tokens the answer uses: question
    tokens from memory, document tokens decrypted from phi_tokens under the tenant key."""
    answer, n = reid.restore(state["answer_deid"], state.get("phi_map", {}),
                             state.get("token_index", {}), state["tenant_id"])
    return {"answer": answer, "validation": {**state.get("validation", {}), "tokens_restored": n}}


def fail(state: State) -> State:
    return {"answer": "", "errors": state.get("errors", []) + ["validation_failed"]}


def no_chunks(state: State) -> State:
    return {"answer": "", "validation": {"ok": False, "reason": "no_chunks"},
            "errors": state.get("errors", []) + ["no_chunks"]}


def query_outcome(state: State) -> tuple[str, dict]:
    """(action, detail) for the audit_log row of a finished query.

    job.query.completed: the answer passed validation and was re-identified for the caller.
    job.query.rejected:  nothing was delivered; detail["reasons"] names the failed checks
    ("phi_leak", "cites_chunks", "grounded") or "no_chunks". Both actions share one detail
    shape so the trail can be queried uniformly. It never contains answer text."""
    v = state.get("validation") or {}
    attempts = state.get("attempts") or 0
    delivered = bool(state.get("answer")) and bool(v.get("ok"))
    reasons = []
    if v.get("phi_leak"):
        reasons.append("phi_leak")
    if v.get("cites_chunks") is False:
        reasons.append("cites_chunks")
    if v.get("grounded") is False:
        reasons.append("grounded")
    if v.get("reason"):
        reasons.append(v["reason"])                       # no_chunks
    detail = {
        "reasons": reasons,
        "phi_leak": v.get("phi_leak"), "cites_chunks": v.get("cites_chunks"), "grounded": v.get("grounded"),
        "faithfulness": v.get("faithfulness"),
        "attempts": attempts, "escalated": attempts > 1,
        "escalation_skipped": v.get("escalation_skipped"),
        "tokens_restored": v.get("tokens_restored", 0),
        "chunks_read": len(state.get("chunks", [])),
        "phi_reidentified": bool(state.get("answer")),
    }
    return (QUERY_COMPLETED if delivered else QUERY_REJECTED), detail


def _write_query_audit(state: State, action: str, detail: dict) -> None:
    """The job row exactly as store.audit writes it (status, result, tokens, cost), plus the
    outcome-specific audit_log row. store.audit hard-codes job.<kind>.completed, so the query
    path writes its own row; ingest still goes through store.audit."""
    usage = state.get("usage", {})
    with store.tenant_conn(state["tenant_id"]) as con:
        con.execute(
            "UPDATE jobs SET status=%s, result=%s, tokens_small=%s, tokens_large=%s, cost_cents=%s, finished_at=now() WHERE id=%s",
            ("failed" if state.get("errors") else "done",
             Jsonb({"answer": state.get("answer"), "validation": state.get("validation"),
                    "citations": [c["id"] for c in state.get("chunks", [])],
                    "errors": state.get("errors") or []}),
             usage.get("small", 0), usage.get("large", 0), llm.cost_cents(usage), state["job_id"]))
        con.execute(
            "INSERT INTO audit_log (tenant_id, api_key_id, job_id, actor, action, patient_id, detail) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (state["tenant_id"], state["api_key_id"], state["job_id"], "worker", action,
             state.get("patient_id"), Jsonb(detail)))


def audit(state: State) -> State:
    if state.get("kind") == "query":
        action, detail = query_outcome(state)
        _write_query_audit(state, action, detail)
    else:
        store.audit(state)                                # ingest: job.ingest.completed, unchanged
    return {}


# ---------------------------------------------------------------- build graphs
def build_ingest() -> StateGraph:
    g = StateGraph(State)
    for name, fn in [("load", load), ("route_pages", route_pages), ("extract", extract_pages),
                     ("deidentify", deidentify), ("annotate", annotate_pages),
                     ("chunk_embed", chunk_embed), ("audit", audit)]:
        g.add_node(name, fn)
    g.set_entry_point("load")
    g.add_edge("load", "route_pages"); g.add_edge("route_pages", "extract")
    g.add_edge("extract", "deidentify"); g.add_edge("deidentify", "annotate")
    g.add_edge("annotate", "chunk_embed")
    g.add_edge("chunk_embed", "audit"); g.add_edge("audit", END)
    return g


def build_query() -> StateGraph:
    g = StateGraph(State)
    for name, fn in [("deidentify_q", deidentify_question), ("retrieve", retrieve),
                     ("generate", generate), ("validate", validate), ("reidentify", reidentify),
                     ("fail", fail), ("no_chunks", no_chunks), ("audit", audit)]:
        g.add_node(name, fn)
    g.set_entry_point("deidentify_q")
    g.add_edge("deidentify_q", "retrieve")
    g.add_conditional_edges("retrieve", after_retrieve, {"generate": "generate", "no_chunks": "no_chunks"})
    g.add_edge("generate", "validate")
    g.add_conditional_edges("validate", after_validate,
                            {"reidentify": "reidentify", "generate": "generate", "fail": "fail"})
    g.add_edge("reidentify", "audit"); g.add_edge("fail", "audit"); g.add_edge("no_chunks", "audit")
    g.add_edge("audit", END)
    return g
