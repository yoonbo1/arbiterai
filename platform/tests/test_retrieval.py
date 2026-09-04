"""worker/retrieval.hybrid with the database and the embedding service replaced by fakes: the
SQL and its bind parameters are inspected and the BM25 + reciprocal-rank-fusion scores are
checked against hand-computed values. Also covers the store helpers hybrid() depends on."""
from contextlib import contextmanager

import pytest

from worker import retrieval, store

TENANT = "tenant-A"
PATIENT = "patient-7"
QVEC = [0.25] * store.EMBED_DIM

# (id, page, section, text, sim) in the order Postgres returns them: by vector distance.
# BM25 tokenizes with \w+, so terms glued to punctuation still match.
ROWS = [
    (101, 1, "# Hospital course", "Overnight vitals stable, no acute events.", 0.95),
    (102, 2, "# Medications", "Started on ceftriaxone 1 g IV daily for pneumonia of the right lung.", 0.90),
    (103, 2, None, "Chest x-ray shows pneumonia in the right lower lobe.", 0.85),
    (104, 3, "# Activity", "Ambulating in the hallway without assistance.", 0.80),
    (105, 3, None, "Diet advanced as tolerated.", 0.75),
]


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return list(self.rows)


class FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return FakeCursor(self.rows)


class FakeDB:
    def __init__(self):
        self.rows: list[tuple] = []
        self.tenants: list[str] = []
        self.embedded: list[list[str]] = []
        self.conn: FakeConn | None = None


@pytest.fixture
def fake_db(monkeypatch):
    """Patch store.embed and store.tenant_conn (looked up via the module at call time)."""
    db = FakeDB()

    def embed(texts):
        db.embedded.append(list(texts))
        return [list(QVEC) for _ in texts]

    @contextmanager
    def tenant_conn(tenant_id):
        db.tenants.append(tenant_id)
        db.conn = FakeConn(db.rows)
        yield db.conn

    monkeypatch.setattr(store, "embed", embed)
    monkeypatch.setattr(store, "tenant_conn", tenant_conn)
    return db


def run(db, query, **kw):
    return retrieval.hybrid(tenant_id=TENANT, patient_id=PATIENT, query=query, **kw)


# ---------------------------------------------------------------- scoping

def test_query_is_hard_filtered_by_tenant_and_patient(fake_db):
    fake_db.rows = ROWS
    run(fake_db, "ceftriaxone", k=3, pool=30)

    assert fake_db.tenants == [TENANT]                 # RLS context set for this tenant only
    assert fake_db.embedded == [["ceftriaxone"]]       # one embedding call, for the query only
    assert len(fake_db.conn.executed) == 1
    sql, params = fake_db.conn.executed[0]
    assert "FROM chunks WHERE tenant_id=%s AND patient_id=%s" in sql
    assert "ORDER BY embedding <=> %s::vector LIMIT %s" in sql
    lit = store.vector_literal(QVEC)
    assert params == (lit, TENANT, PATIENT, lit, 30)   # bound parameters, never interpolated
    assert TENANT not in sql and PATIENT not in sql


def test_pool_size_is_the_sql_limit(fake_db):
    fake_db.rows = ROWS
    run(fake_db, "x", pool=7)
    assert fake_db.conn.executed[0][1][-1] == 7


# ---------------------------------------------------------------- fusion

def test_bm25_lifts_exact_term_match_over_higher_vector_similarity(fake_db):
    fake_db.rows = ROWS
    out = run(fake_db, "ceftriaxone pneumonia", k=5)
    assert [d["id"] for d in out] == [102, 103, 101, 104, 105]
    # 102: vector rank 1, BM25 rank 0 (both terms); 103: vector rank 2, BM25 rank 1 (one term);
    # 101: vector rank 0 but no lexical overlap, so no BM25 contribution at all
    assert out[0]["score"] == pytest.approx(1 / 61 + 1 / 60)
    assert out[1]["score"] == pytest.approx(1 / 62 + 1 / 61)
    assert out[2]["score"] == pytest.approx(1 / 60)
    assert out[0]["sim"] < out[2]["sim"]               # the winner had the lower vector similarity


def test_scores_are_rrf_sums_sorted_descending(fake_db):
    fake_db.rows = ROWS
    out = run(fake_db, "ceftriaxone pneumonia", k=10)
    scores = [d["score"] for d in out]
    assert scores == sorted(scores, reverse=True)
    # recompute RRF independently from the two rankings
    vec_rank = {r[0]: i for i, r in enumerate(ROWS)}
    bm_rank = {102: 0, 103: 1}                          # only chunks with lexical overlap
    for d in out:
        expected = 1 / (60 + vec_rank[d["id"]]) + (1 / (60 + bm_rank[d["id"]]) if d["id"] in bm_rank else 0)
        assert d["score"] == pytest.approx(expected)
    assert all(0 < d["score"] <= 2 / 60 for d in out)


def test_no_lexical_overlap_keeps_vector_order(fake_db):
    fake_db.rows = ROWS
    out = run(fake_db, "zzzqqq", k=10)
    assert [d["id"] for d in out] == [r[0] for r in ROWS]
    assert out[0]["score"] == pytest.approx(1 / 60)   # vector contribution only


def test_results_are_limited_to_k(fake_db):
    fake_db.rows = ROWS
    assert len(run(fake_db, "pneumonia", k=2)) == 2
    assert len(run(fake_db, "pneumonia", k=1)) == 1
    assert len(run(fake_db, "pneumonia", k=50)) == len(ROWS)
    assert run(fake_db, "pneumonia", k=0) == []


def test_empty_result_set_returns_empty_list(fake_db):
    fake_db.rows = []
    assert run(fake_db, "anything") == []
    assert fake_db.tenants == [TENANT]                 # the scoped query was still issued


def test_result_shape(fake_db):
    fake_db.rows = ROWS
    out = run(fake_db, "pneumonia", k=2)
    for d in out:
        assert set(d) == {"id", "page", "section", "text", "sim", "score", "document_id"}
        assert isinstance(d["sim"], float) and isinstance(d["score"], float)
    assert out[0]["text"] in {r[3] for r in ROWS}


def test_blank_chunk_text_does_not_break_bm25(fake_db):
    """A blank chunk is tokenized as [''] so BM25's average document length is never zero."""
    fake_db.rows = [(1, 1, None, "", 0.9), (2, 1, None, "ceftriaxone given", 0.8)]
    out = run(fake_db, "ceftriaxone", k=5)
    assert {d["id"] for d in out} == {1, 2}
    assert all(d["score"] > 0 for d in out)
    # every chunk blank: without the guard this raises ZeroDivisionError inside rank_bm25
    fake_db.rows = [(1, 1, None, "", 0.9), (2, 1, None, "   ", 0.8)]
    assert [d["id"] for d in run(fake_db, "ceftriaxone", k=5)] == [1, 2]


def test_bm25_matches_term_followed_by_punctuation(fake_db):
    fake_db.rows = [(201, 1, None, "Overnight vitals stable.", 0.95),
                    (202, 1, None, "Started on ceftriaxone.", 0.90),
                    (203, 1, None, "Ambulating independently.", 0.85)]
    out = run(fake_db, "ceftriaxone", k=3)
    assert out[0]["id"] == 202


# ---------------------------------------------------------------- store helpers used by hybrid()

def test_vector_literal_is_pgvector_syntax():
    assert store.vector_literal([0.1, 1, -2.5]) == "[0.1,1.0,-2.5]"
    assert store.vector_literal([]) == "[]"
    lit = store.vector_literal(QVEC)
    assert lit.startswith("[") and lit.endswith("]")
    assert lit.count(",") == store.EMBED_DIM - 1
    assert [float(x) for x in lit[1:-1].split(",")] == QVEC


def test_embed_batches_requests_and_concatenates(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, n):
            self.n = n

        def raise_for_status(self):
            pass

        def json(self):
            return [list(QVEC) for _ in range(self.n)]

    def post(url, json, timeout):
        calls.append((url, len(json["inputs"]), json["truncate"]))
        return Resp(len(json["inputs"]))

    monkeypatch.setattr(store.httpx, "post", post)
    out = store.embed([f"chunk {i}" for i in range(70)])
    assert len(out) == 70 and all(len(v) == store.EMBED_DIM for v in out)
    assert [n for _, n, _ in calls] == [32, 32, 6]
    assert all(url == f"{store.EMBED_URL}/embed" and truncate is True for url, _, truncate in calls)
    assert store.embed([]) == []


def test_embed_rejects_wrong_dimension(monkeypatch):
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return [[0.0] * 10]

    monkeypatch.setattr(store.httpx, "post", lambda *a, **k: Resp())
    with pytest.raises(ValueError, match=r"embedding dim 10 != 384"):
        store.embed(["x"])
