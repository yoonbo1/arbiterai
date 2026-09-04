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
CHUNK_SIZE, CHUNK_OVERLAP = 800, 120
splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
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


def split_with_offsets(text: str) -> list[tuple[str, int | None, int | None]]:
    """Chunk one page and return (piece, char_start, char_end) with text[char_start:char_end] == piece.
    The splitter keeps separators and only strips whitespace, so every piece is a verbatim substring.
    Consecutive pieces overlap by at most CHUNK_OVERLAP characters, so the next piece cannot start
    before the previous end minus that (minus a little stripped whitespace); searching from there,
    not from the previous start, keeps repeated lines (forms, vitals flowsheets) from matching a
    copy that comes too early."""
    out, cursor = [], 0
    for piece in splitter.split_text(text):
        pos = text.find(piece, cursor)
        if pos < 0:
            pos = text.find(piece)
        if pos < 0 or text[pos:pos + len(piece)] != piece:      # cannot happen; keep the row, lose the offsets
            out.append((piece, None, None))
            continue
        out.append((piece, pos, pos + len(piece)))
        cursor = max(pos + 1, pos + len(piece) - CHUNK_OVERLAP - 64)
    return out


def chunk_for(chunks: list[tuple[int, int | None, int | None]], start: int, end: int) -> int | None:
    """The chunk (id, char_start, char_end) on the same page whose range overlaps [start, end) most."""
    best, best_ov = None, 0
    for cid, s, e in chunks:
        if s is None or e is None:
            continue
        ov = min(e, end) - max(s, start)
        if ov > best_ov:
            best, best_ov = cid, ov
    return best


def _fact_field(f, name):
    return f[name] if isinstance(f, dict) else getattr(f, name)


def index_document(*, tenant_id, patient_id, document_id, pages, texts, phi_map, facts=None) -> int:
    assert len(pages) == len(texts), f"{len(pages)} pages but {len(texts)} texts"
    facts = facts if facts is not None else [[] for _ in pages]
    assert len(facts) == len(pages), f"{len(pages)} pages but {len(facts)} fact lists"
    rows = []                                              # (page, section, piece, route, char_start, char_end)
    for page, text in zip(pages, texts):
        for piece, s, e in split_with_offsets(text):
            section = piece.split("\n", 1)[0][:80] if piece.startswith("#") else None
            rows.append((page.number, section, piece, page.route, s, e))
    vecs = embed([r[2] for r in rows]) if rows else []
    with tenant_conn(tenant_id) as con, con.cursor() as cur:   # psycopg3: executemany lives on the cursor
        # Re-ingest is idempotent: derived rows of this document are replaced, not appended.
        cur.execute("DELETE FROM clinical_facts WHERE document_id=%s", (document_id,))
        cur.execute("DELETE FROM chunks WHERE document_id=%s", (document_id,))
        cur.execute("DELETE FROM phi_tokens WHERE document_id=%s", (document_id,))
        chunk_ids: list[int] = []
        if rows:
            cur.executemany(
                "INSERT INTO chunks (tenant_id, patient_id, document_id, page, section, text, embedding, extraction, "
                "char_start, char_end) VALUES (%s,%s,%s,%s,%s,%s,%s::vector,%s,%s,%s) RETURNING id",
                [(tenant_id, patient_id, document_id, r[0], r[1], r[2], vector_literal(v), r[3], r[4], r[5])
                 for r, v in zip(rows, vecs)], returning=True)
            while True:
                chunk_ids.append(cur.fetchone()[0])
                if not cur.nextset():
                    break
        by_page: dict[int, list[tuple[int, int | None, int | None]]] = {}
        for r, cid in zip(rows, chunk_ids):
            by_page.setdefault(r[0], []).append((cid, r[4], r[5]))
        # Facts cite the chunk on their page that overlaps their span most (NULL when none does).
        fact_rows = []
        for page, page_facts in zip(pages, facts):
            for f in page_facts:
                s, e = _fact_field(f, "start"), _fact_field(f, "end")
                fact_rows.append((tenant_id, patient_id, document_id, chunk_for(by_page.get(page.number, []), s, e),
                                  page.number, _fact_field(f, "section"), _fact_field(f, "kind"),
                                  _fact_field(f, "text"), _fact_field(f, "normalized"),
                                  Jsonb(_fact_field(f, "attributes") or {}), _fact_field(f, "assertion"),
                                  _fact_field(f, "date_token"), float(_fact_field(f, "confidence")),
                                  _fact_field(f, "extractor"), s, e))
        cur.executemany(
            "INSERT INTO clinical_facts (tenant_id, patient_id, document_id, chunk_id, page, section, kind, text, "
            "normalized, attributes, assertion, date_token, confidence, extractor, span_start, span_end) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", fact_rows)
        cur.executemany(
            "INSERT INTO phi_tokens (tenant_id, document_id, token, entity_type, value_enc) "
            "VALUES (%s,%s,%s,%s, pgp_sym_encrypt(%s, %s)) ON CONFLICT DO NOTHING",
            [(tenant_id, document_id, tok, tok.strip("<>").rsplit("_", 1)[0], val, _tenant_key(tenant_id))
             for tok, val in phi_map.items()])
        cur.execute("UPDATE documents SET status='indexed', pages=%s WHERE id=%s", (len(pages), document_id))
    return len(rows)


def decrypt_tokens(tenant_id: str, document_id: str, tokens: list[str]) -> dict[str, str]:
    """Re-identification for the authorized caller: decrypt exactly the requested placeholder
    tokens of one document. Runs under app.tenant_id so RLS applies, with the tenant's key."""
    if not tokens or not document_id:
        return {}
    with tenant_conn(tenant_id) as con:
        rows = con.execute(
            "SELECT token, pgp_sym_decrypt(value_enc, %s) FROM phi_tokens "
            "WHERE document_id=%s AND token = ANY(%s)",
            (_tenant_key(tenant_id), document_id, list(tokens))).fetchall()
    return {t: v for t, v in rows}


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
                    if state.get("kind") == "ingest" else None,
                    "facts": (state.get("validation") or {}).get("facts") if state.get("kind") == "ingest" else None})))
