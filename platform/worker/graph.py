"""LangGraph pipelines. Two graphs share one state schema:

  ingest:  load -> route_pages -> extract(text|ocr|vlm) -> deidentify -> chunk_embed -> audit
  query:   deidentify_q -> retrieve -> generate(small) -> validate -> [escalate(large) -> validate] -> reidentify -> audit

Invariant enforced in code: nothing leaves this process to a model endpoint unless
state["deidentified"] is True.  Tenant id is set in the first node and never changes.

Graphs are compiled by worker.main with the checkpointer chosen by CHECKPOINTER
(default none). State holds pre-de-identification text and the plaintext phi_map, so a
persistent checkpointer must not be used with real data until that state is protected.
"""
from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from . import deid, extract, llm, retrieval, store


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
    # query
    question: str
    question_deid: str
    max_chunks: int
    chunks: list[dict]
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


def chunk_embed(state: State) -> State:
    assert state["deidentified"], "refusing to embed non-de-identified text"
    n = store.index_document(
        tenant_id=state["tenant_id"], patient_id=state["patient_id"],
        document_id=state["document_id"], pages=state["pages"], texts=state["raw_text"],
        phi_map=state["phi_map"],
    )
    return {"validation": {"chunks_indexed": n, "pages": len(state["pages"]),
                           "vlm_wanted_pages": sum(1 for p in state["pages"] if p.vlm_wanted)}}


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
    return {"chunks": chunks}


def after_retrieve(state: State) -> Literal["generate", "no_chunks"]:
    return "generate" if state.get("chunks") else "no_chunks"


def generate(state: State) -> State:
    assert state["deidentified"]
    tier = "large" if state.get("attempts", 0) > 0 else "small"
    answer, used = llm.answer(tier, state["question_deid"], state["chunks"])
    usage = dict(state["usage"]); usage[tier] = usage.get(tier, 0) + used
    return {"answer_deid": answer, "usage": usage, "attempts": state.get("attempts", 0) + 1}


def validate(state: State) -> State:
    """Reject answers that leak PHI, cite nothing, or have low grounding."""
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
    v["ok"] = (not v["phi_leak"]) and v["cites_chunks"] and v["grounded"]
    return {"validation": v, "usage": usage}


def after_validate(state: State) -> Literal["reidentify", "generate", "fail"]:
    if state["validation"]["ok"]:
        return "reidentify"
    if state["validation"]["phi_leak"] or state["attempts"] >= 2:
        return "fail"                      # never loop on a leak; escalate at most once
    return "generate"


def reidentify(state: State) -> State:
    # Only the caller's own patient's tokens get swapped back, at the very last step.
    return {"answer": deid.restore(state["answer_deid"], state["phi_map"])}


def fail(state: State) -> State:
    return {"answer": "", "errors": state.get("errors", []) + ["validation_failed"]}


def no_chunks(state: State) -> State:
    return {"answer": "", "validation": {"ok": False, "reason": "no_chunks"},
            "errors": state.get("errors", []) + ["no_chunks"]}


def audit(state: State) -> State:
    store.audit(state)
    return {}


# ---------------------------------------------------------------- build graphs
def build_ingest() -> StateGraph:
    g = StateGraph(State)
    for name, fn in [("load", load), ("route_pages", route_pages), ("extract", extract_pages),
                     ("deidentify", deidentify), ("chunk_embed", chunk_embed), ("audit", audit)]:
        g.add_node(name, fn)
    g.set_entry_point("load")
    g.add_edge("load", "route_pages"); g.add_edge("route_pages", "extract")
    g.add_edge("extract", "deidentify"); g.add_edge("deidentify", "chunk_embed")
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
