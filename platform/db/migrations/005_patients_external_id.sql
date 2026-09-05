-- patients.external_id (the tenant's MRN) was plaintext although init.sql said "stored encrypted
-- at rest" (TODO item 10). It is replaced by two columns:
--   external_id_hash  HMAC-SHA256 (hex) of the id under a key derived from the tenant key
--                     (worker/tenant_keys.py); every lookup by external id (ingest, query,
--                     GET /v1/patients/{id}/facts) uses it;
--   external_id_enc   pgp_sym_encrypt(id, tenant key); decrypted only to hand the id back to
--                     the caller that presented it.
--
-- Existing rows cannot be converted here: the hash and the ciphertext need TENANT_KEK, which
-- psql does not have (and must not). The only database this code has run against holds
-- synthetic data, so the legacy patient rows are dropped together with their documents (chunks,
-- phi_tokens and clinical_facts cascade from documents); `make eval` re-ingests the corpus.
-- Tenants, keys, jobs and audit rows are untouched. A deployment with real records would
-- instead backfill the two columns from a process that holds the key, then drop external_id.
-- Idempotent; on a fresh database init.sql already has the new columns and this is a no-op.
ALTER TABLE patients
  ADD COLUMN IF NOT EXISTS external_id_hash text,
  ADD COLUMN IF NOT EXISTS external_id_enc  bytea;
DO $$ DECLARE n bigint;
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'patients' AND column_name = 'external_id') THEN
    SELECT count(*) INTO n FROM patients WHERE external_id_hash IS NULL;
    RAISE NOTICE 'dropping % legacy patient row(s) and their documents (synthetic data; no key in psql)', n;
    DELETE FROM documents WHERE patient_id IN (SELECT id FROM patients WHERE external_id_hash IS NULL);
    DELETE FROM patients  WHERE external_id_hash IS NULL;
    ALTER TABLE patients DROP CONSTRAINT IF EXISTS patients_tenant_id_external_id_key;
    ALTER TABLE patients DROP COLUMN external_id;
  END IF;
END $$;
ALTER TABLE patients ALTER COLUMN external_id_hash SET NOT NULL;
ALTER TABLE patients ALTER COLUMN external_id_enc  SET NOT NULL;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'patients_tenant_id_external_id_hash_key') THEN
    ALTER TABLE patients ADD CONSTRAINT patients_tenant_id_external_id_hash_key UNIQUE (tenant_id, external_id_hash);
  END IF;
END $$;
