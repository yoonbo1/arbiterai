"""db/init.sql and db/migrations: no plaintext request, result or patient id column survives,
audit_log is under the tenant_isolation policy, and no SQL in the services still names the old
columns. Read from the files, so this holds for a fresh database and for a migrated one."""
import ast
import re
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[1]
INIT = (PLATFORM / "db" / "init.sql").read_text()
MIGRATIONS = {p.name: p.read_text() for p in sorted((PLATFORM / "db" / "migrations").glob("*.sql"))}


def table(name: str) -> str:
    m = re.search(rf"CREATE TABLE {name} \((.*?)\n\);", INIT, re.S)
    assert m, f"CREATE TABLE {name} not found"
    return m.group(1)


def columns(block: str) -> dict[str, str]:
    """column name -> the rest of its definition line, comments stripped."""
    out = {}
    for line in block.splitlines():
        line = line.split("--", 1)[0].strip().rstrip(",")
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isidentifier() and parts[0] not in ("UNIQUE", "PRIMARY", "CHECK"):
            out[parts[0]] = parts[1]
    return out


# ---------------------------------------------------------------- jobs

def test_jobs_has_no_plaintext_request_or_result_column():
    cols = columns(table("jobs"))
    assert "request" not in cols and "result" not in cols
    assert cols["request_enc"].startswith("bytea NOT NULL")
    assert cols["result_enc"].startswith("bytea")
    assert not any(t.startswith("jsonb") and c in ("request", "result") for c, t in cols.items())


def test_jobs_migration_drops_the_plaintext_columns_and_says_why():
    m = MIGRATIONS["004_jobs_encrypt.sql"]
    assert "ADD COLUMN IF NOT EXISTS request_enc bytea" in m and "ADD COLUMN IF NOT EXISTS result_enc" in m
    assert "DROP COLUMN IF EXISTS request" in m and "DROP COLUMN IF EXISTS result" in m
    assert "NOT re-encrypted" in m and "synthetic" in m            # the decision is written down


# ---------------------------------------------------------------- patients

def test_patients_holds_a_keyed_hash_and_ciphertext_not_the_id():
    block = table("patients")
    cols = columns(block)
    assert "external_id" not in cols
    assert cols["external_id_hash"].startswith("text NOT NULL")
    assert cols["external_id_enc"].startswith("bytea NOT NULL")
    assert "UNIQUE (tenant_id, external_id_hash)" in block


def test_patients_migration_replaces_the_column_and_documents_the_data_loss():
    m = MIGRATIONS["005_patients_external_id.sql"]
    assert "ADD COLUMN IF NOT EXISTS external_id_hash text" in m and "external_id_enc  bytea" in m
    assert "DROP COLUMN external_id" in m and "column_name = 'external_id'" in m    # guarded: runs once
    assert "UNIQUE (tenant_id, external_id_hash)" in m
    assert "synthetic" in m and "TENANT_KEK" in m


# ---------------------------------------------------------------- documents

def test_documents_storage_uri_is_nullable_and_content_hash_is_of_the_bytes():
    block = table("documents")
    cols = columns(block)
    assert cols["storage_uri"] == "text"                              # cleared on a failed ingest
    assert cols["content_hash"].startswith("text NOT NULL")
    assert "sha256" in block and "md5" not in INIT
    m = MIGRATIONS["006_documents_hash_and_failed_ingest.sql"]
    assert "ALTER COLUMN storage_uri DROP NOT NULL" in m


# ---------------------------------------------------------------- audit_log

def test_audit_log_is_tenant_scoped_and_append_only():
    cols = columns(table("audit_log"))
    assert cols["tenant_id"].startswith("uuid NOT NULL")
    assert re.search(r"ALTER TABLE audit_log\s+ENABLE ROW LEVEL SECURITY", INIT)
    policy_tables = re.search(r"FOREACH t IN ARRAY ARRAY\[(.*?)\]", INIT).group(1)
    assert "'audit_log'" in policy_tables                               # same tenant_isolation policy as PHI tables
    assert "REVOKE UPDATE, DELETE ON audit_log FROM app_rw" in INIT
    m = MIGRATIONS["003_audit_log_rls.sql"]
    assert "ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY" in m
    assert "CREATE POLICY tenant_isolation ON audit_log" in m and "policyname = 'tenant_isolation'" in m
    assert "USING (tenant_id = current_setting('app.tenant_id', true)::uuid)" in m
    assert "WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)" in m
    assert "REVOKE UPDATE, DELETE ON audit_log FROM app_rw" in m


# ---------------------------------------------------------------- migrations are applied in order

def test_migrations_003_to_006_exist_and_are_picked_up():
    assert list(MIGRATIONS) == ["001_clinical_facts.sql", "002_chunk_offsets.sql", "003_audit_log_rls.sql",
                                "004_jobs_encrypt.sql", "005_patients_external_id.sql",
                                "006_documents_hash_and_failed_ingest.sql"]
    runner = (PLATFORM / "db" / "03_apply_migrations.sh").read_text()
    assert "/docker-entrypoint-initdb.d/migrations/*.sql" in runner and "schema_migrations" in runner


# ---------------------------------------------------------------- no service SQL names the old columns

def sql_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and re.search(r"\b(FROM|INTO|UPDATE)\s+(jobs|patients|documents)\b", n.value)]


def test_no_service_sql_reads_or_writes_a_plaintext_column():
    old = re.compile(r"\b(request|result|external_id)\b(?!_enc|_hash)")
    for rel in ("gateway/main.py", "worker/store.py", "worker/main.py", "eval/run_eval.py",
                "eval/run_extraction_eval.py"):
        for lit in sql_literals(PLATFORM / rel):
            # `AS result` / `AS external_id` only name the decrypted output column of the SELECT.
            body = re.sub(r"\bAS (result|external_id)\b", "", lit)
            assert not old.search(body), (rel, lit)
