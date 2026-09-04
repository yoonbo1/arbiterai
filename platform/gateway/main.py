"""API gateway: authenticates tenants, enqueues jobs, never runs inference inline.

Connects to Postgres as the application role (app_rw), which is subject to row-level
security; the owner role would silently bypass RLS."""
import asyncio, json, os, uuid
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import auth

STREAM = "jobs"


async def _init_conn(con: asyncpg.Connection) -> None:
    # asyncpg returns json/jsonb as raw strings unless codecs are registered.
    for t in ("json", "jsonb"):
        await con.set_type_codec(t, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=2, max_size=20, init=_init_conn)
    app.state.redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    yield
    await app.state.pool.close()
    await app.state.redis.aclose()


app = FastAPI(title="HIPAA doc AI gateway", lifespan=lifespan)


def _uuid(value: str, what: str = "id") -> str:
    """Client-supplied ids reach SQL as uuid parameters; reject malformed ones as 404, not 500."""
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(404, f"{what} not found")


async def principal(request: Request, authorization: str = Header(...)) -> auth.Principal:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    p = await auth.resolve(request.app.state.pool, request.app.state.redis, authorization[7:])
    if not p:
        raise HTTPException(401, "invalid, expired, or revoked key")
    if await auth.rate_limited(request.app.state.redis, p):
        raise HTTPException(429, "rate limit exceeded")
    return p


def require(scope: str):
    async def dep(p: auth.Principal = Depends(principal)):
        if scope not in p.scopes and "admin" not in p.scopes:
            raise HTTPException(403, f"key lacks scope '{scope}'")
        return p
    return dep


async def enqueue(request: Request, p: auth.Principal, kind: str, payload: dict, idem: str | None) -> str:
    job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{p.api_key_id}:{idem}")) if idem else str(uuid.uuid4())
    async with request.app.state.pool.acquire() as con, con.transaction():
        await con.execute("SELECT set_config('app.tenant_id', $1, true)", p.tenant_id)
        inserted = await con.fetchval(
            """INSERT INTO jobs (id, tenant_id, api_key_id, kind, request)
               VALUES ($1,$2,$3,$4,$5) ON CONFLICT (id) DO NOTHING RETURNING id""",
            job_id, p.tenant_id, p.api_key_id, kind, payload)          # dict: jsonb codec encodes it
        if inserted:
            await con.execute(
                "INSERT INTO audit_log (tenant_id, api_key_id, job_id, actor, action, detail) VALUES ($1,$2,$3,$4,$5,$6)",
                p.tenant_id, p.api_key_id, job_id, p.key_prefix, f"job.{kind}.submitted", {"idem": idem})
    if inserted:  # idempotent replay skips re-enqueue
        await request.app.state.redis.xadd(STREAM, {"job_id": job_id, "tenant_id": p.tenant_id, "kind": kind})
    return job_id


class IngestRequest(BaseModel):
    patient_external_id: str = Field(min_length=1, max_length=200)
    doc_type: str | None = Field(None, max_length=100)
    storage_uri: str = Field(min_length=1, max_length=1000,
                             description="Path in the tenant's encrypted bucket/volume (must be under DATA_ROOT)")


class QueryRequest(BaseModel):
    patient_external_id: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=4000)
    max_chunks: int = Field(6, ge=1, le=20)


@app.post("/v1/documents", status_code=202)
async def ingest(body: IngestRequest, request: Request, p=Depends(require("ingest")),
                 idempotency_key: str | None = Header(None)):
    return {"job_id": await enqueue(request, p, "ingest", body.model_dump(), idempotency_key)}


@app.post("/v1/queries", status_code=202)
async def query(body: QueryRequest, request: Request, p=Depends(require("query")),
                idempotency_key: str | None = Header(None)):
    return {"job_id": await enqueue(request, p, "query", body.model_dump(), idempotency_key)}


@app.get("/v1/jobs/{job_id}")
async def job_status(job_id: str, request: Request, p=Depends(principal)):
    job_id = _uuid(job_id, "job")
    async with request.app.state.pool.acquire() as con, con.transaction():
        await con.execute("SELECT set_config('app.tenant_id', $1, true)", p.tenant_id)
        row = await con.fetchrow("SELECT status, result, finished_at FROM jobs WHERE id=$1", job_id)
    if not row:
        raise HTTPException(404, "job not found")   # RLS makes other tenants' jobs invisible
    return {"job_id": job_id, "status": row["status"], "result": row["result"], "finished_at": row["finished_at"]}


FACT_KINDS = ("problem", "medication", "lab", "vital", "procedure", "allergy", "immunization", "referral", "plan", "other")
INACTIVE_ASSERTIONS = ("absent", "family", "conditional", "possible")


@app.get("/v1/patients/{external_id}/facts")
async def patient_facts(external_id: str, request: Request, kind: str | None = Query(None),
                        active: bool = Query(True), limit: int = Query(500, ge=1, le=5000),
                        p=Depends(require("query"))):
    """Structured, de-identified clinical facts for one patient (the evidence-packet primitive).
    Text is stored de-identified (<PERSON_1> placeholders); nothing is re-identified here.
    active=true (default) hides facts asserted absent, family-history, conditional or possible."""
    if kind is not None and kind not in FACT_KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(FACT_KINDS)}")
    sql = ("SELECT id, document_id, chunk_id, page, section, kind, text, normalized, attributes, assertion, "
           "date_token, confidence, extractor FROM clinical_facts WHERE patient_id=$1")
    params: list = []
    if kind is not None:
        params.append(kind); sql += f" AND kind=${len(params) + 1}"
    if active:
        params.append(list(INACTIVE_ASSERTIONS)); sql += f" AND NOT (assertion = ANY(${len(params) + 1}::text[]))"
    params.append(limit); sql += f" ORDER BY page, span_start, id LIMIT ${len(params) + 1}"
    async with request.app.state.pool.acquire() as con, con.transaction():
        await con.execute("SELECT set_config('app.tenant_id', $1, true)", p.tenant_id)
        pid = await con.fetchval("SELECT id FROM patients WHERE external_id=$1", external_id)
        if not pid:
            raise HTTPException(404, "patient not found")    # RLS: other tenants' patients are invisible
        rows = await con.fetch(sql, pid, *params)
        await con.execute(
            "INSERT INTO audit_log (tenant_id, api_key_id, actor, action, patient_id, detail) VALUES ($1,$2,$3,$4,$5,$6)",
            p.tenant_id, p.api_key_id, p.key_prefix, "facts.read", pid,
            {"count": len(rows), "kind": kind, "active": active, "limit": limit})
    return {"patient_external_id": external_id, "count": len(rows), "active_only": active, "facts": [
        {"id": r["id"], "document_id": str(r["document_id"]), "chunk_id": r["chunk_id"], "page": r["page"],
         "section": r["section"], "kind": r["kind"], "text": r["text"], "normalized": r["normalized"],
         "attributes": r["attributes"] or {}, "assertion": r["assertion"], "date_token": r["date_token"],
         "confidence": float(r["confidence"]), "extractor": r["extractor"]} for r in rows]}


# ---- Admin: tenant & key management (protect behind VPN/IP allowlist + MFA in prod) ----
class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    baa_signed: bool = False


class KeyCreate(BaseModel):
    scopes: list[str] = ["query"]
    rate_limit_per_min: int = Field(60, ge=1, le=100000)


def admin(x_admin_token: str = Header(...)):
    if x_admin_token != os.environ["ADMIN_TOKEN"]:
        raise HTTPException(403, "bad admin token")


@app.post("/admin/tenants", dependencies=[Depends(admin)])
async def create_tenant(body: TenantCreate, request: Request):
    tid = await request.app.state.pool.fetchval(
        "INSERT INTO tenants (name, baa_signed_at) VALUES ($1, CASE WHEN $2 THEN now() END) RETURNING id",
        body.name, body.baa_signed)
    return {"tenant_id": str(tid)}


@app.post("/admin/tenants/{tenant_id}/keys", dependencies=[Depends(admin)])
async def create_key(tenant_id: str, body: KeyCreate, request: Request):
    tenant_id = _uuid(tenant_id, "tenant")
    plaintext, prefix, h = auth.new_key()
    try:
        kid = await request.app.state.pool.fetchval(
            """INSERT INTO api_keys (tenant_id, key_prefix, key_hash, scopes, rate_limit_per_min)
               VALUES ($1,$2,$3,$4,$5) RETURNING id""", tenant_id, prefix, h, body.scopes, body.rate_limit_per_min)
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(404, "tenant not found")
    await request.app.state.pool.execute(
        "INSERT INTO audit_log (tenant_id, api_key_id, actor, action) VALUES ($1,$2,'admin','key.created')", tenant_id, kid)
    return {"key_id": str(kid), "api_key": plaintext, "note": "Shown once. Store securely."}


@app.delete("/admin/keys/{key_id}", dependencies=[Depends(admin)])
async def revoke_key(key_id: str, request: Request):
    key_id = _uuid(key_id, "key")
    row = await request.app.state.pool.fetchrow(
        "UPDATE api_keys SET revoked_at=now() WHERE id=$1 AND revoked_at IS NULL RETURNING tenant_id, key_hash", key_id)
    if row:
        await request.app.state.redis.delete(f"key:{row['key_hash']}")
        await request.app.state.pool.execute(
            "INSERT INTO audit_log (tenant_id, api_key_id, actor, action) VALUES ($1,$2,'admin','key.revoked')", row["tenant_id"], key_id)
    return {"revoked": bool(row)}


@app.get("/healthz")
async def healthz(request: Request):
    """Liveness + dependency check used by the compose healthcheck."""
    checks = {}
    try:
        checks["postgres"] = await asyncio.wait_for(request.app.state.pool.fetchval("SELECT 1"), 3) == 1
    except Exception as e:
        checks["postgres"] = f"error: {type(e).__name__}"
    try:
        checks["redis"] = bool(await asyncio.wait_for(request.app.state.redis.ping(), 3))
    except Exception as e:
        checks["redis"] = f"error: {type(e).__name__}"
    ok = all(v is True for v in checks.values())
    return JSONResponse({"ok": ok, **checks}, status_code=200 if ok else 503)
