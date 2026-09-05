"""worker/store.py persistence helpers with the database replaced by a recording fake: patient
and document upserts, job load / finish / fail, and the content hash. Every encrypt or decrypt
goes through pgp_sym_* with the tenant key from worker/tenant_keys.py."""
import hashlib
import json
import os
from contextlib import contextmanager

import pytest

from worker import store
from worker.tenant_keys import external_id_hash, tenant_key

TENANT = "11111111-1111-4111-8111-111111111111"
PATIENT = "33333333-3333-4333-8333-333333333333"
DOC = "44444444-4444-4444-8444-444444444444"
JOB = "55555555-5555-4555-8555-555555555555"
KEY = tenant_key(TENANT)


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [self.row] if self.row is not None else []


class FakeConn:
    """execute() records (sql, params); fetchone() on the returned cursor yields the next scripted row."""

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.executed: list[tuple[str, tuple | None]] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return FakeCursor(self.rows.pop(0) if self.rows else None)


@pytest.fixture
def db(monkeypatch):
    """store.tenant_conn replaced: hands out one FakeConn per transaction and records the tenant."""
    state = {"conn": None, "rows": [], "tenants": []}

    @contextmanager
    def tenant_conn(tenant_id):
        state["tenants"].append(tenant_id)
        state["conn"] = FakeConn(state["rows"])
        yield state["conn"]

    monkeypatch.setattr(store, "tenant_conn", tenant_conn)
    return state


# ---------------------------------------------------------------- content hash

def test_sha256_file_hashes_the_bytes_streaming(tmp_path):
    data = os.urandom(2_500_000)                                    # > one 1 MiB read block
    f = tmp_path / "doc.pdf"
    f.write_bytes(data)
    assert store.sha256_file(f) == hashlib.sha256(data).hexdigest()
    assert store.sha256_file(f) != store.sha256_file(tmp_path / "other.pdf") if (tmp_path / "other.pdf").write_bytes(b"x") else True


def test_sha256_file_is_of_content_not_path(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"same bytes")
    (tmp_path / "b.pdf").write_bytes(b"same bytes")
    assert store.sha256_file(tmp_path / "a.pdf") == store.sha256_file(tmp_path / "b.pdf")


# ---------------------------------------------------------------- patients

def test_upsert_patient_binds_hash_and_ciphertext_never_a_plaintext_column():
    con = FakeConn([(PATIENT,)])
    assert store.upsert_patient(con, TENANT, "P00001") == PATIENT
    sql, params = con.executed[0]
    assert "INSERT INTO patients (tenant_id, external_id_hash, external_id_enc)" in sql
    assert "pgp_sym_encrypt(%s, %s)" in sql and "ON CONFLICT (tenant_id, external_id_hash)" in sql
    assert "external_id)" not in sql and "external_id=" not in sql
    assert params == (TENANT, external_id_hash(TENANT, "P00001"), "P00001", KEY)
    assert "P00001" not in sql                                       # bound, never interpolated


# ---------------------------------------------------------------- documents

def upsert(con, **kw):
    return store.upsert_document(con, tenant_id=TENANT, patient_id=PATIENT, doc_type="discharge_summary",
                                 storage_uri="/data/synthetic/clean/P00001.pdf", content_hash="ab" * 32, **kw)


def test_upsert_document_reuses_the_row_with_the_same_bytes():
    con = FakeConn([(DOC,)])                                          # content match on the first SELECT
    assert upsert(con) == DOC
    sqls = [s for s, _ in con.executed]
    assert sqls[0].startswith("SELECT id FROM documents WHERE tenant_id=%s AND content_hash=%s")
    assert con.executed[0][1] == (TENANT, "ab" * 32)
    assert sqls[1].startswith("UPDATE documents SET status='processing'")
    assert con.executed[1][1] == (PATIENT, "discharge_summary", "/data/synthetic/clean/P00001.pdf", "ab" * 32, DOC)
    assert len(sqls) == 2                                            # no INSERT


def test_upsert_document_treats_new_bytes_at_a_known_path_as_a_new_version():
    con = FakeConn([None, (DOC,)])                                    # no content match, path match
    assert upsert(con) == DOC
    sqls = [s for s, _ in con.executed]
    assert "AND storage_uri=%s" in sqls[1] and con.executed[1][1] == (TENANT, "/data/synthetic/clean/P00001.pdf")
    assert sqls[2].startswith("UPDATE documents SET") and "content_hash=%s" in sqls[2]


def test_upsert_document_inserts_when_unknown():
    con = FakeConn([None, None, (DOC,)])
    assert upsert(con) == DOC
    sql, params = con.executed[2]
    assert sql.startswith("INSERT INTO documents (tenant_id, patient_id, doc_type, storage_uri, content_hash, status)")
    assert "md5(" not in sql and params == (TENANT, PATIENT, "discharge_summary", "/data/synthetic/clean/P00001.pdf", "ab" * 32)


def test_fail_document_clears_the_client_supplied_uri(db):
    store.fail_document(TENANT, DOC)
    assert db["tenants"] == [TENANT]
    sql, params = db["conn"].executed[0]
    assert "SET status='failed', storage_uri=NULL" in sql and params == (DOC,)


# ---------------------------------------------------------------- jobs

def test_get_job_decrypts_the_request_under_the_tenant_key(db):
    req = {"patient_external_id": "P00001", "question": "HbA1c?", "max_chunks": 6}
    db["rows"][:] = [("key-1", "query", json.dumps(req))]
    j = store.get_job(JOB, TENANT)
    assert j == {"api_key_id": "key-1", "kind": "query", "request": req}
    sql, params = db["conn"].executed[0]
    assert "pgp_sym_decrypt(request_enc, %s)" in sql and "SELECT api_key_id, kind," in sql
    assert params == (KEY, JOB)
    assert db["conn"].executed[1][0].startswith("UPDATE jobs SET status='processing'")


def test_get_job_none_when_invisible_and_request_none_for_legacy_rows(db):
    assert store.get_job(JOB, TENANT) is None
    assert len(db["conn"].executed) == 1                             # never marked processing
    db["rows"][:] = [("key-1", "ingest", None)]                       # request_enc NULL (pre-004 row)
    assert store.get_job(JOB, TENANT)["request"] is None


def test_fail_job_records_the_reason_encrypted_and_never_overwrites_done(db):
    store.fail_job(JOB, TENANT, "FileNotFoundError")
    sql, params = db["conn"].executed[0]
    assert "result_enc=pgp_sym_encrypt(%s, %s)" in sql and "AND status<>'done'" in sql
    assert params == (json.dumps({"error": "FileNotFoundError"}), KEY, JOB)
    assert "result=" not in sql


def test_audit_encrypts_the_result_and_writes_a_tenant_scoped_audit_row(db):
    state = {"job_id": JOB, "tenant_id": TENANT, "api_key_id": "key-1", "kind": "query", "patient_id": PATIENT,
             "answer": "HbA1c is 9.0% [7]", "validation": {"ok": True, "attempts": 1},
             "chunks": [{"id": 7}, {"id": 9}], "errors": [], "usage": {"small": 120}, "attempts": 1}
    store.audit(state)
    assert db["tenants"] == [TENANT]
    (upd_sql, upd), (aud_sql, aud) = db["conn"].executed
    assert upd_sql.startswith("UPDATE jobs SET status=%s, result_enc=pgp_sym_encrypt(%s, %s)")
    assert upd[0] == "done" and upd[2] == KEY and upd[-1] == JOB
    assert json.loads(upd[1]) == {"answer": "HbA1c is 9.0% [7]", "validation": {"ok": True, "attempts": 1},
                                  "citations": [7, 9], "errors": []}
    assert isinstance(upd[1], str)                                   # text into pgp_sym_encrypt, not jsonb
    assert "INSERT INTO audit_log (tenant_id," in aud_sql and aud[0] == TENANT and aud[4] == "job.query.completed"
    assert "9.0%" not in repr(aud)                                   # the answer is not in the audit detail


def test_audit_marks_failed_when_the_graph_recorded_errors(db):
    store.audit({"job_id": JOB, "tenant_id": TENANT, "api_key_id": "k", "kind": "query",
                 "answer": "", "errors": ["validation_failed"], "usage": {}})
    assert db["conn"].executed[0][1][0] == "failed"
