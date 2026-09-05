"""GET /v1/patients/{external_id}/facts on the FastAPI app with the asyncpg pool replaced by a
recording fake and the principal dependency overridden (no network, no database). The patient
is looked up by the keyed hash of the external id; the id handed back comes from the decrypted
column, not from the URL."""
from contextlib import asynccontextmanager

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("asyncpg")
from fastapi.testclient import TestClient  # noqa: E402

import auth  # noqa: E402
import main as gateway  # noqa: E402
from worker.tenant_keys import external_id_hash, tenant_key  # noqa: E402

PID = "33333333-3333-4333-8333-333333333333"
ROWS = [
    {"id": 1, "document_id": "44444444-4444-4444-8444-444444444444", "chunk_id": 7, "page": 1, "section": "medications",
     "kind": "medication", "text": "metformin 500 mg BID", "normalized": "metformin",
     "attributes": {"dose": "500 mg", "frequency": "BID"}, "assertion": "present", "date_token": "<DATE_TIME_1>",
     "confidence": 0.95, "extractor": "rules"},
    {"id": 2, "document_id": "44444444-4444-4444-8444-444444444444", "chunk_id": None, "page": 1, "section": "diagnoses",
     "kind": "problem", "text": "COPD", "normalized": "copd", "attributes": None, "assertion": "present",
     "date_token": None, "confidence": 0.75, "extractor": "ner"},
]


class FakeCon:
    def __init__(self, patient_id, rows):
        self.patient_id, self.rows, self.calls = patient_id, rows, []
        self.external_id = "P00000"           # what pgp_sym_decrypt(external_id_enc, key) yields

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        return {"id": self.patient_id, "external_id": self.external_id} if self.patient_id else None

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        return self.rows


class FakePool:
    def __init__(self, con):
        self.con = con

    @asynccontextmanager
    async def acquire(self):
        yield self.con


@pytest.fixture
def client():
    con = FakeCon(PID, ROWS)
    gateway.app.state.pool = FakePool(con)
    p = auth.Principal("tenant-1", "key-1", "hipaa_live_x", ["query"], 100)
    gateway.app.dependency_overrides[gateway.principal] = lambda: p
    try:
        yield TestClient(gateway.app), con
    finally:
        gateway.app.dependency_overrides.clear()


def test_facts_default_is_active_only(client):
    c, con = client
    r = c.get("/v1/patients/P00000/facts", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["patient_external_id"] == "P00000" and j["count"] == 2 and j["active_only"] is True
    assert j["facts"][0] == {**ROWS[0], "document_id": ROWS[0]["document_id"]}
    assert j["facts"][1]["attributes"] == {}                       # NULL attributes -> {}
    kinds = [k for k, *_ in con.calls]
    assert kinds == ["execute", "fetchrow", "fetch", "execute"]
    assert con.calls[0][1].startswith("SELECT set_config('app.tenant_id'") and con.calls[0][2] == ("tenant-1",)
    lookup_sql, lookup_args = con.calls[1][1], con.calls[1][2]
    assert "FROM patients WHERE external_id_hash=$1" in lookup_sql
    assert "pgp_sym_decrypt(external_id_enc, $2)" in lookup_sql
    assert lookup_args == (external_id_hash("tenant-1", "P00000"), tenant_key("tenant-1"))
    assert "P00000" not in lookup_args and "P00000" not in lookup_sql   # only the keyed hash reaches SQL
    fetch_sql, fetch_args = con.calls[2][1], con.calls[2][2]
    assert "WHERE patient_id=$1" in fetch_sql and "NOT (assertion = ANY($2::text[]))" in fetch_sql
    assert fetch_args == (PID, ["absent", "family", "conditional", "possible"], 500)
    audit_sql, audit_args = con.calls[3][1], con.calls[3][2]
    assert "INSERT INTO audit_log" in audit_sql
    assert audit_args[3] == "facts.read" and audit_args[4] == PID and audit_args[5]["count"] == 2


def test_facts_kind_filter_and_inactive(client):
    c, con = client
    r = c.get("/v1/patients/P00000/facts?kind=problem&active=false&limit=10", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    fetch_sql, fetch_args = con.calls[2][1], con.calls[2][2]
    assert "AND kind=$2" in fetch_sql and "ANY(" not in fetch_sql          # no assertion filter
    assert fetch_args == (PID, "problem", 10)


def test_facts_rejects_unknown_kind(client):
    c, _ = client
    assert c.get("/v1/patients/P00000/facts?kind=banana", headers={"Authorization": "Bearer x"}).status_code == 422
    assert c.get("/v1/patients/P00000/facts?limit=0", headers={"Authorization": "Bearer x"}).status_code == 422


def test_facts_unknown_patient_is_404_and_not_audited(client):
    c, con = client
    con.patient_id = None
    r = c.get("/v1/patients/NOPE/facts", headers={"Authorization": "Bearer x"})
    assert r.status_code == 404
    assert [k for k, *_ in con.calls] == ["execute", "fetchrow"]


def test_facts_returns_the_decrypted_external_id_from_the_row(client):
    c, con = client
    con.external_id = "MRN-FROM-DB"
    r = c.get("/v1/patients/P00000/facts", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200 and r.json()["patient_external_id"] == "MRN-FROM-DB"


def test_facts_requires_query_scope(client):
    c, _ = client
    gateway.app.dependency_overrides[gateway.principal] = lambda: auth.Principal("tenant-1", "k", "hipaa_live_x", ["ingest"], 100)
    assert c.get("/v1/patients/P00000/facts", headers={"Authorization": "Bearer x"}).status_code == 403
