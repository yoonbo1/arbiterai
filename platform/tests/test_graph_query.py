"""Query-graph outcomes (worker/graph.py): which audit action a finished query writes, when a
failed draft is escalated to the large tier, and the single-escalation guard.

Every out-of-process call is replaced: the model (llm.answer, llm.faithfulness_score), retrieval,
the scrubber, and the database (store.tenant_conn records the statements the audit node runs).
Re-identification (worker/reid.py) is real; the answers only use question tokens, which are
restored from memory, so store.decrypt_tokens is never reached."""
import json
import sys
import types
from contextlib import contextmanager

import pytest


def _stub_missing_worker_deps() -> list[str]:
    """worker/graph.py imports langgraph and worker/extract.py imports pytesseract. CI installs
    worker/requirements.txt and gets the real ones; the host venv may lack them. Stub only what
    is missing, so the same tests run against real LangGraph where it exists, and return the
    stubbed module names so the caller can take them out of sys.modules again."""
    stubbed = []
    try:
        import langgraph.graph  # noqa: F401
    except ImportError:
        END = "__end__"

        class _App:
            def __init__(self, g):
                self.g = g

            def invoke(self, state, config=None):
                state, node = dict(state), self.g.entry
                for _ in range(25):                        # LangGraph's default recursion limit
                    state.update(self.g.nodes[node](state) or {})
                    if node in self.g.branches:
                        fn, mapping = self.g.branches[node]
                        node = mapping[fn(state)]
                    else:
                        node = self.g.edges[node]
                    if node is END:
                        return state
                raise RecursionError("graph did not reach END within 25 steps")

        class _StateGraph:
            def __init__(self, schema):
                self.nodes, self.edges, self.branches, self.entry = {}, {}, {}, None

            def add_node(self, name, fn):
                self.nodes[name] = fn

            def set_entry_point(self, name):
                self.entry = name

            def add_edge(self, src, dst):
                self.edges[src] = dst

            def add_conditional_edges(self, src, fn, mapping):
                self.branches[src] = (fn, mapping)

            def compile(self, checkpointer=None):
                return _App(self)

        pkg, mod = types.ModuleType("langgraph"), types.ModuleType("langgraph.graph")
        mod.END, mod.StateGraph = END, _StateGraph
        pkg.graph = mod
        sys.modules["langgraph"], sys.modules["langgraph.graph"] = pkg, mod
        stubbed += ["langgraph", "langgraph.graph"]
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        sys.modules["pytesseract"] = types.ModuleType("pytesseract")
        stubbed.append("pytesseract")
    return stubbed


_STUBBED = _stub_missing_worker_deps()

from worker import graph, llm, store  # noqa: E402

for _name in _STUBBED:      # worker.graph keeps what it imported; other tests' importorskip
    sys.modules.pop(_name)  # ("could not import langgraph", tests/test_annotate.py) stays honest

DOC = "aaaaaaaa-0000-0000-0000-000000000001"
DIFFERENT_TIERS = {"small": ("http://small:8000/v1", "qwen2.5:7b-instruct"),
                   "large": ("http://large:8000/v1", "qwen2.5:72b-instruct")}
IDENTICAL_TIERS = {"small": ("http://host:11434/v1", "qwen2.5:7b-instruct"),
                   "large": ("http://host:11434/v1", "qwen2.5:7b-instruct")}
CITED = "Dr. <PERSON_1> started metformin 500 mg BID [7]"     # cites chunk 7, uses the question's token
UNCITED = "Metformin 500 mg BID was started."                 # no citation marker at all
LEAKED = "Metformin was started; SSN 123-45-6789 [7]"         # cited and grounded, but raw PHI


def chunk(cid, text):
    return {"id": cid, "document_id": DOC, "page": 1, "section": None, "text": text, "sim": 0.9, "score": 0.02}


class FakeConn:
    """Records what the audit node executes. `.job` and `.audit` unpack the two statements."""

    def __init__(self):
        self.executed: list[tuple[str, tuple]] = []
        self.tenants: list[str] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    def _one(self, prefix):
        rows = [c for c in self.executed if c[0].startswith(prefix)]
        assert len(rows) == 1, f"expected exactly one {prefix!r}, got {len(rows)}"
        return rows[0][1]

    @property
    def job(self):
        p = self._one("UPDATE jobs SET")
        return {"status": p[0], "result": p[1].obj, "tokens_small": p[2], "tokens_large": p[3], "job_id": p[5]}

    @property
    def audit(self):
        p = self._one("INSERT INTO audit_log")
        return {"action": p[4], "detail": p[6].obj, "patient_id": p[5], "actor": p[3]}


@pytest.fixture
def db(monkeypatch):
    conn = FakeConn()

    @contextmanager
    def tenant_conn(tenant_id):
        conn.tenants.append(tenant_id)
        yield conn

    monkeypatch.setattr(store, "tenant_conn", tenant_conn)
    monkeypatch.setattr(store, "decrypt_tokens", lambda *a: pytest.fail("document tokens must not be decrypted here"))
    monkeypatch.setattr(store, "audit", lambda state: pytest.fail("the query path must not use store.audit"))
    return conn


@pytest.fixture
def pipeline(monkeypatch):
    """Deterministic stand-ins. `cfg["answers"]` / `cfg["scores"]` are consumed per generation /
    judge call; `calls["answer"]` records the tier of every generation."""
    cfg = {"answers": [], "scores": [], "chunks": [chunk(7, "Attending: Dr. <PERSON_1>. Started metformin 500 mg BID."),
                                                  chunk(8, "Allergies: none.")],
           "phi": lambda text: "123-45-6789" in text}
    calls = {"answer": [], "judge": []}

    def scrub(question):
        return question.replace("Patel", "<PERSON_1>"), ({"<PERSON_1>": "Patel"} if "Patel" in question else {})

    def answer(tier, question, chunks):
        assert "Patel" not in question and all("Patel" not in c["text"] for c in chunks)
        calls["answer"].append(tier)
        return cfg["answers"].pop(0), 100

    def judge(text, chunks):
        calls["judge"].append(text)
        return cfg["scores"].pop(0), 20

    monkeypatch.setattr(graph.deid, "scrub", scrub)
    monkeypatch.setattr(graph.deid, "contains_phi", lambda text: cfg["phi"](text))
    monkeypatch.setattr(graph.retrieval, "hybrid", lambda **kw: [dict(c) for c in cfg["chunks"]])
    monkeypatch.setattr(llm, "answer", answer)
    monkeypatch.setattr(llm, "faithfulness_score", judge)
    monkeypatch.setattr(llm, "TIERS", DIFFERENT_TIERS)
    return cfg, calls


def run_query():
    return graph.build_query().compile().invoke({
        "job_id": "job-1", "tenant_id": "tenant-1", "api_key_id": "key-1", "kind": "query",
        "patient_id": "patient-1", "question": "What did Dr. Patel start?", "max_chunks": 6})


# ------------------------------------------------------------------ audit actions
def test_delivered_answer_writes_job_query_completed(db, pipeline):
    cfg, calls = pipeline
    cfg["answers"], cfg["scores"] = [CITED], [1.0]
    final = run_query()
    assert calls["answer"] == ["small"]
    assert final["answer"] == "Dr. Patel started metformin 500 mg BID [7]"     # re-identified from memory
    assert db.tenants == ["tenant-1"] and db.job["job_id"] == "job-1"
    assert db.job["status"] == "done"
    assert db.job["result"]["answer"] == final["answer"] and db.job["result"]["errors"] == []
    assert db.job["result"]["citations"] == [7, 8]
    v = db.job["result"]["validation"]
    assert v["ok"] and v["attempts"] == 1 and v["escalated"] is False and "escalation_skipped" not in v
    assert db.audit["action"] == graph.QUERY_COMPLETED == "job.query.completed"
    assert db.audit["actor"] == "worker" and db.audit["patient_id"] == "patient-1"
    assert db.audit["detail"] == {
        "reasons": [], "phi_leak": False, "cites_chunks": True, "grounded": True, "faithfulness": 1.0,
        "attempts": 1, "escalated": False, "escalation_skipped": None, "tokens_restored": 1,
        "chunks_read": 2, "phi_reidentified": True}
    assert "Patel" not in json.dumps(db.audit["detail"])                       # the trail carries no PHI


def test_failed_validation_with_differing_tiers_escalates_once_then_rejects(db, pipeline):
    cfg, calls = pipeline
    cfg["answers"], cfg["scores"] = [UNCITED, UNCITED], [0.2, 0.3]
    final = run_query()
    assert calls["answer"] == ["small", "large"]                               # exactly one escalation
    assert final["answer"] == "" and final["errors"] == ["validation_failed"]
    assert db.job["status"] == "failed"                                        # unchanged job semantics
    assert db.job["result"]["answer"] == "" and db.job["result"]["errors"] == ["validation_failed"]
    assert db.job["tokens_small"] == 100 + 20 + 20 and db.job["tokens_large"] == 100
    v = db.job["result"]["validation"]
    assert v["attempts"] == 2 and v["escalated"] is True and "escalation_skipped" not in v   # eval counts attempts > 1
    assert db.audit["action"] == graph.QUERY_REJECTED == "job.query.rejected"
    assert db.audit["detail"] == {
        "reasons": ["cites_chunks", "grounded"], "phi_leak": False, "cites_chunks": False, "grounded": False,
        "faithfulness": 0.3, "attempts": 2, "escalated": True, "escalation_skipped": None,
        "tokens_restored": 0, "chunks_read": 2, "phi_reidentified": False}


def test_identical_tiers_skip_escalation_and_reject_at_one_attempt(db, pipeline, monkeypatch):
    cfg, calls = pipeline
    monkeypatch.setattr(llm, "TIERS", IDENTICAL_TIERS)
    cfg["answers"], cfg["scores"] = [UNCITED, "never used"], [0.2, 9.9]
    run_query()
    assert calls["answer"] == ["small"]                                        # no second generation
    assert cfg["answers"] == ["never used"]
    v = db.job["result"]["validation"]
    assert v["escalation_skipped"] == graph.ESCALATION_SKIPPED_IDENTICAL_TIERS == "large tier identical to small tier"
    assert v["attempts"] == 1 and v["escalated"] is False                      # not counted as an escalation
    assert db.job["status"] == "failed" and db.job["tokens_large"] == 0
    assert db.audit["action"] == "job.query.rejected"
    d = db.audit["detail"]
    assert d["reasons"] == ["cites_chunks", "grounded"]
    assert d["escalated"] is False and d["escalation_skipped"] == "large tier identical to small tier"


def test_phi_leak_is_a_rejection_reason_and_never_escalates(db, pipeline):
    cfg, calls = pipeline
    cfg["answers"], cfg["scores"] = [LEAKED, "never used"], [1.0, 1.0]
    run_query()
    assert calls["answer"] == ["small"]                                        # a leak is never retried
    assert db.job["status"] == "failed" and db.job["result"]["answer"] == ""
    assert db.audit["action"] == "job.query.rejected"
    d = db.audit["detail"]
    assert d["reasons"] == ["phi_leak"] and d["phi_leak"] is True
    assert d["cites_chunks"] is True and d["grounded"] is True                 # the leak alone rejected it
    assert d["escalated"] is False and d["escalation_skipped"] is None         # not a tier decision
    leaked = "123-45-6789"
    assert leaked not in json.dumps(db.job["result"]) and leaked not in json.dumps(d)


def test_no_chunks_is_rejected_not_completed(db, pipeline):
    cfg, calls = pipeline
    cfg["chunks"] = []
    run_query()
    assert calls["answer"] == [] and calls["judge"] == []
    assert db.job["status"] == "failed" and db.job["result"]["errors"] == ["no_chunks"]
    assert db.audit["action"] == "job.query.rejected"
    assert db.audit["detail"]["reasons"] == ["no_chunks"] and db.audit["detail"]["chunks_read"] == 0


def test_ingest_audit_still_goes_through_store_audit(db, monkeypatch):
    seen = []
    monkeypatch.setattr(store, "audit", lambda state: seen.append(state))
    state = {"kind": "ingest", "job_id": "job-2", "tenant_id": "tenant-1", "api_key_id": "key-1"}
    assert graph.audit(state) == {}
    assert seen == [state] and db.executed == []                               # nothing written directly


# ------------------------------------------------------- the single-escalation guard
def failed_validation(attempts, **extra):
    return {"validation": {"ok": False, "phi_leak": False, "cites_chunks": False, "grounded": False,
                           "faithfulness": 0.0, "attempts": attempts, **extra}, "attempts": attempts}


def test_at_most_one_escalation_is_an_explicit_guard(monkeypatch):
    assert graph.MAX_ESCALATIONS == 1 and graph.MAX_GENERATIONS == 2
    monkeypatch.setattr(llm, "TIERS", DIFFERENT_TIERS)
    assert graph.after_validate(failed_validation(1)) == "generate"            # the one permitted escalation
    assert graph.after_validate(failed_validation(2)) == "fail"                # budget spent
    assert graph.after_validate(failed_validation(1, phi_leak=True)) == "fail"
    assert graph.after_validate(failed_validation(1, escalation_skipped="large tier identical to small tier")) == "fail"
    assert graph.after_validate({"validation": {"ok": True, "phi_leak": False, "attempts": 1}, "attempts": 1}) == "reidentify"
    # generate() refuses a third generation even if routing were wrong, before any model call.
    monkeypatch.setattr(llm, "answer", lambda *a: pytest.fail("no model call past the limit"))
    with pytest.raises(graph.EscalationLimitExceeded):
        graph.generate({"deidentified": True, "attempts": 2, "question_deid": "q", "chunks": [], "usage": {}})


def test_end_to_end_never_generates_more_than_twice(db, pipeline):
    cfg, calls = pipeline
    cfg["answers"], cfg["scores"] = [UNCITED] * 5, [0.0] * 5                   # the judge never passes
    run_query()
    assert calls["answer"] == ["small", "large"] and len(cfg["answers"]) == 3
    assert db.audit["action"] == "job.query.rejected" and db.audit["detail"]["attempts"] == 2


# ------------------------------------------------------------------ tier identity rule
def test_tiers_identical_compares_resolved_endpoint_and_model(monkeypatch):
    monkeypatch.setattr(llm, "TIERS", IDENTICAL_TIERS)
    assert llm.tiers_identical()
    monkeypatch.setattr(llm, "TIERS", {"small": ("http://h:11434/v1/", "qwen2.5:7b-instruct "),
                                       "large": ("http://h:11434/v1", "qwen2.5:7b-instruct")})
    assert llm.tiers_identical()                                               # slash and whitespace only
    monkeypatch.setattr(llm, "TIERS", DIFFERENT_TIERS)
    assert not llm.tiers_identical()
    monkeypatch.setattr(llm, "TIERS", {"small": ("http://h:11434/v1", "qwen2.5:7b-instruct"),
                                       "large": ("http://h:11434/v1", "qwen2.5:72b-instruct")})
    assert not llm.tiers_identical()                                           # same endpoint, larger model
    monkeypatch.setattr(llm, "TIERS", {"small": ("http://h:11434/v1", "qwen2.5:7b-instruct"),
                                       "large": ("http://gpu:8000/v1", "qwen2.5:7b-instruct")})
    assert not llm.tiers_identical()                                           # same model, other endpoint


def test_large_tier_unset_falls_back_to_small_and_is_identical():
    # conftest sets SMALL_MODEL_URL only; LARGE_MODEL_URL / LARGE_MODEL are unset, so the large
    # tier resolves to the small one and escalation would be a paid rerun.
    assert llm.TIERS["large"] == llm.TIERS["small"] and llm.tiers_identical()
