"""Hybrid retrieval scoped to (tenant, patient). Vector + BM25 fused with RRF."""
import re

from rank_bm25 import BM25Okapi

from . import store


_WORD = re.compile(r"\w+")


def tokenize(text: str) -> list[str]:
    r"""BM25 tokens. \w+ so 'ceftriaxone.' at a sentence end still matches 'ceftriaxone'."""
    return _WORD.findall(text.lower())


def hybrid(*, tenant_id: str, patient_id: str, query: str, k: int = 6, pool: int = 30) -> list[dict]:
    qvec = store.vector_literal(store.embed([query])[0])
    with store.tenant_conn(tenant_id) as con:
        rows = con.execute(
            """SELECT id, page, section, text, 1 - (embedding <=> %s::vector) AS sim, document_id
                 FROM chunks WHERE tenant_id=%s AND patient_id=%s
                ORDER BY embedding <=> %s::vector LIMIT %s""",
            (qvec, tenant_id, patient_id, qvec, pool)).fetchall()
    if not rows:
        return []
    docs = [{"id": r[0], "page": r[1], "section": r[2], "text": r[3], "sim": float(r[4]),
             "document_id": str(r[5]) if len(r) > 5 and r[5] is not None else None} for r in rows]
    bm25 = BM25Okapi([tokenize(d["text"]) or [""] for d in docs])
    bm = bm25.get_scores(tokenize(query))
    vec_rank = {d["id"]: i for i, d in enumerate(docs)}
    # Only chunks with lexical overlap are "returned" by the BM25 list; a zero-score chunk
    # must not collect a rank-based bonus just for being first in vector order, or an
    # exact-term match could never outrank the top vector hit.
    bm_order = [i for i in sorted(range(len(docs)), key=lambda i: -bm[i]) if bm[i] > 0]
    bm_rank = {docs[i]["id"]: r for r, i in enumerate(bm_order)}
    for d in docs:   # reciprocal rank fusion (k=60)
        d["score"] = 1 / (60 + vec_rank[d["id"]])
        if d["id"] in bm_rank:
            d["score"] += 1 / (60 + bm_rank[d["id"]])
    return sorted(docs, key=lambda d: -d["score"])[:k]
