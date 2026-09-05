-- audit_log under row-level security (TODO item 6). Until now app_rw held SELECT on the whole
-- table: append-only, but every tenant's rows were readable from any tenant's session. The same
-- tenant_isolation policy as the PHI tables now scopes SELECT and INSERT to app.tenant_id.
--
-- Every writer runs on a connection with app.tenant_id set: the gateway on job submit and on the
-- facts endpoint, the worker on job completion, and the admin key endpoints, which record
-- key.created / key.revoked under the tenant the key belongs to (gateway/main.py). So there are
-- no tenant-less rows and the column becomes NOT NULL; a system-level event with no tenant
-- belongs in the service logs, not here. Idempotent.
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'audit_log' AND policyname = 'tenant_isolation') THEN
    CREATE POLICY tenant_isolation ON audit_log
      USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
      WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
  END IF;
END $$;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM audit_log WHERE tenant_id IS NULL) THEN
    RAISE EXCEPTION 'audit_log has rows without tenant_id; the owner must assign them before this migration';
  END IF;
END $$;
ALTER TABLE audit_log ALTER COLUMN tenant_id SET NOT NULL;
-- Append-only stays append-only.
REVOKE UPDATE, DELETE ON audit_log FROM app_rw;
