"""Postgres/pgvector persistence. Every connection sets app.tenant_id so RLS applies.
The pool is created lazily so importing this module (e.g. in tests) needs no database."""
import json, os, threading
from contextlib import contextmanager

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from . import llm

EMBED_URL = (os.environ.get("EMBED_URL") or "http://embeddings:80").rstrip("/")
EMBED_DIM = 384          # chunks.embedding is vector(384); change both together
splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120,
                                          separators=["\n## ", "\n# ", "\n\n", "\n", ". ", " "])

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                _pool = ConnectionPool(os.environ["DATABASE_URL"], min_size=1, max_size=8, open=True)
    return _pool


@contextmanager
def tenant_conn(tenant_id: str):
    """One transaction with app.tenant_id set (transaction-local, so it never leaks to the
    next borrower of the pooled connection)."""
    with get_pool().connection() as con, con.transaction():
        con.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant_id,))
        yield con


def embed(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), 32):
        r = httpx.post(f"{EMBED_URL}/embed", json={"inputs": texts[i:i + 32], "truncate": True}, timeout=120)
        r.raise_for_status()
        out.extend(r.json())
    if out and len(out[0]) != EMBED_DIM:
        raise ValueError(f"embedding dim {len(out[0])} != {EMBED_DIM}; EMBED_MODEL and chunks.embedding disagree")
    return out


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


def index_document(*, tenant_id, patient_id, document_id, pages, texts, phi_map) -> int:
    assert len(pages) == len(texts), f"{len(pages)} pages but {len(texts)} texts"
    rows = []
    for page, text in zip(pages, texts):
        for piece in splitter.split_text(text):
            section = piece.split("\n", 1)[0][:80] if piece.startswith("#") else None
            rows.append((page.number, section, piece, page.route))
    vecs = embed([r[2] for r in rows]) if rows else []
    with tenant_conn(tenant_id) as con, con.cursor() as cur:   # psycopg3: executemany lives on the cursor
        # Re-ingest is idempotent: derived rows of this document are replaced, not appended.
        cur.execute("DELETE FROM chunks WHERE document_id=%s", (document_id,))
        cur.execute("DELETE FROM phi_tokens WHERE document_id=%s", (document_id,))
        cur.executemany(
            "INSERT INTO chunks (tenant_id, patient_id, document_id, page, section, text, embedding, extraction) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s::vector,%s)",
            [(tenant_id, patient_id, document_id, r[0], r[1], r[2], vector_literal(v), r[3]) for r, v in zip(rows, vecs)])
        cur.executemany(
            "INSERT INTO phi_tokens (tenant_id, document_id, token, entity_type, value_enc) "
            "VALUES (%s,%s,%s,%s, pgp_sym_encrypt(%s, %s)) ON CONFLICT DO NOTHING",
            [(tenant_id, document_id, tok, tok.strip("<>").rsplit("_", 1)[0], val, _tenant_key(tenant_id))
             for tok, val in phi_map.items()])
        cur.execute("UPDATE documents SET status='indexed', pages=%s WHERE id=%s", (len(pages), document_id))
    return len(rows)


def _tenant_key(tenant_id: str) -> str:
    # Local dev: derive from env. Prod: fetch per-tenant DEK from KMS/Vault, cached briefly.
    kek = os.environ.get("TENANT_KEK")
    if not kek:
        raise RuntimeError("TENANT_KEK is not set; refusing to encrypt the PHI map with a default key")
    return kek + tenant_id


def audit(state: dict) -> None:
    usage = state.get("usage", {})
    with tenant_conn(state["tenant_id"]) as con:
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
            (state["tenant_id"], state["api_key_id"], state["job_id"], "worker",
             f"job.{state['kind']}.completed", state.get("patient_id"),
             Jsonb({"chunks_read": len(state.get("chunks", [])), "attempts": state.get("attempts"),
                    "phi_reidentified": bool(state.get("answer")),
                    "pages": len(state.get("pages", [])) if state.get("kind") == "ingest" else None,
                    "routes": {r: sum(1 for p in state.get("pages", []) if p.route == r)
                               for r in ("text", "ocr", "vlm")} if state.get("kind") == "ingest" else None,
                    "vlm_wanted_pages": sum(1 for p in state.get("pages", []) if getattr(p, "vlm_wanted", False))
                    if state.get("kind") == "ingest" else None})))
