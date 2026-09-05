"""Job submit and status on the FastAPI app with the asyncpg pool and Redis replaced by recording
fakes: the request is stored only through pgp_sym_encrypt under the tenant key, the result is
decrypted only for GET /v1/jobs/{id} with that same key, and the request is never served."""
import json
import uuid
from contextlib import asynccontextmanager

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("asyncpg")
from fastapi.testclient import TestClient  # noqa: E402

import auth  # noqa: E402
import main as gateway  # noqa: E402
from worker.tenant_keys import tenant_key  # noqa: E402

TENANT = "11111111-1111-4111-8111-111111111111"
JOB = "55555555-5555-4555-8555-555555555555"
RESULT = {"answer": "HbA1c 9.0% [7]", "validation": {"ok": True, "attempts": 1}, "citations": [7], "errors": []}


class FakeCon:
    def __init__(self):
        self.calls = []
        self.fetchval_result = JOB            # INSERT ... RETURNING id (None = idempotent replay)
        self.fetchrow_result = None

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", sql, args))
        return self.fetchval_result

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        return self.fetchrow_result


class FakePool:
    def __init__(self, con):
        self.con = con

    @asynccontextmanager
    async def acquire(self):
        yield self.con


class FakeStream:
    def __init__(self):
        self.added = []

    async def xadd(self, stream, fields):
        self.added.append((stream, dict(fields)))


@pytest.fixture
def client():
    con, stream = FakeCon(), FakeStream()
    gateway.app.state.pool = FakePool(con)
    gateway.app.state.redis = stream
    p = auth.Principal(TENANT, "key-1", "hipaa_live_x", ["ingest", "query"], 100)
    gateway.app.dependency_overrides[gateway.principal] = lambda: p
    try:
        yield TestClient(gateway.app), con, stream
    finally:
        gateway.app.dependency_overrides.clear()


H = {"Authorization": "Bearer x"}


# ---------------------------------------------------------------- submit: request encrypted at rest

def test_submit_stores_the_request_only_as_ciphertext_under_the_tenant_key(client):
    c, con, stream = client
    body = {"patient_external_id": "P00001", "question": "What is the HbA1c?", "max_chunks": 6}
    r = c.post("/v1/queries", headers=H, json=body)
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    assert str(uuid.UUID(job_id)) == job_id                            # server-minted (uuid4 without an Idempotency-Key)

    kinds = [k for k, *_ in con.calls]
    assert kinds == ["execute", "fetchval", "execute"]
    assert con.calls[0][1].startswith("SELECT set_config('app.tenant_id'") and con.calls[0][2] == (TENANT,)
    sql, args = con.calls[1][1], con.calls[1][2]
    assert "INSERT INTO jobs" in sql and "request_enc" in sql and "pgp_sym_encrypt($5, $6)" in sql
    assert "kind, request)" not in sql                                 # the plaintext column is gone
    assert args[:4] == (job_id, TENANT, "key-1", "query")
    assert args[4] == json.dumps(body) and args[5] == tenant_key(TENANT)
    assert not any(isinstance(a, dict) for a in args)                  # never bound as jsonb
    audit_sql, audit_args = con.calls[2][1], con.calls[2][2]
    assert "INSERT INTO audit_log" in audit_sql and audit_args[0] == TENANT and audit_args[4] == "job.query.submitted"
    assert "HbA1c" not in json.dumps(audit_args[5])                    # the question is not in the audit detail
    assert stream.added == [("jobs", {"job_id": job_id, "tenant_id": TENANT, "kind": "query"})]


def test_submit_ingest_uses_the_same_path(client):
    c, con, _ = client
    body = {"patient_external_id": "P00001", "doc_type": "discharge_summary", "storage_uri": "/data/x.pdf"}
    assert c.post("/v1/documents", headers=H, json=body).status_code == 202
    sql, args = con.calls[1][1], con.calls[1][2]
    assert "pgp_sym_encrypt($5, $6)" in sql and args[4] == json.dumps(body) and args[5] == tenant_key(TENANT)


def test_idempotent_replay_neither_audits_nor_enqueues(client):
    c, con, stream = client
    con.fetchval_result = None                                         # ON CONFLICT (id) DO NOTHING
    r = c.post("/v1/queries", headers={**H, "Idempotency-Key": "abc"},
               json={"patient_external_id": "P00001", "question": "q"})
    assert r.status_code == 202
    assert [k for k, *_ in con.calls] == ["execute", "fetchval"] and stream.added == []


# ---------------------------------------------------------------- status: result decrypted for the caller only

def test_job_status_decrypts_the_result_with_the_tenant_key(client):
    c, con, _ = client
    con.fetchrow_result = {"status": "done", "result": json.dumps(RESULT), "finished_at": None}
    r = c.get(f"/v1/jobs/{JOB}", headers=H)
    assert r.status_code == 200
    assert r.json() == {"job_id": JOB, "status": "done", "result": RESULT, "finished_at": None}
    assert set(r.json()) == {"job_id", "status", "result", "finished_at"}   # the request is never served
    assert [k for k, *_ in con.calls] == ["execute", "fetchrow"]
    assert con.calls[0][2] == (TENANT,)                                # RLS context before the read
    sql, args = con.calls[1][1], con.calls[1][2]
    assert "pgp_sym_decrypt(result_enc, $2)" in sql and "request" not in sql
    assert args == (JOB, tenant_key(TENANT))


def test_job_status_with_no_result_yet(client):
    c, con, _ = client
    con.fetchrow_result = {"status": "queued", "result": None, "finished_at": None}
    r = c.get(f"/v1/jobs/{JOB}", headers=H)
    assert r.status_code == 200 and r.json()["result"] is None and r.json()["status"] == "queued"


def test_job_status_unknown_or_other_tenants_job_is_404(client):
    c, con, _ = client
    con.fetchrow_result = None                                         # RLS: invisible
    assert c.get(f"/v1/jobs/{JOB}", headers=H).status_code == 404
    assert len(con.calls) == 2
    assert c.get("/v1/jobs/not-a-uuid", headers=H).status_code == 404
    assert len(con.calls) == 2                                         # malformed ids never reach SQL
