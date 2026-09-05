-- jobs.request and jobs.result were plaintext jsonb (TODO item 8): the raw question and patient
-- external id before de-identification, and the re-identified answer. Both are now bytea from
-- pgp_sym_encrypt under the tenant key (the same key as phi_tokens.value_enc, derived in
-- worker/tenant_keys.py): the gateway encrypts the request on submit and decrypts the result
-- only for GET /v1/jobs/{id}; the worker decrypts the request when it loads the job and
-- encrypts the result when it finishes.
--
-- Existing rows are NOT re-encrypted: psql has no TENANT_KEK (and must not), and the only
-- database this code has run against holds synthetic data. Dropping the plaintext columns
-- discards their contents; legacy rows keep status, accounting and timestamps with
-- request_enc / result_enc NULL, and the worker refuses to process a job whose request it
-- cannot read. Idempotent; on a fresh database init.sql already has the encrypted columns.
ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS request_enc bytea,
  ADD COLUMN IF NOT EXISTS result_enc  bytea;
ALTER TABLE jobs
  DROP COLUMN IF EXISTS request,
  DROP COLUMN IF EXISTS result;
-- request_enc is NOT NULL on a fresh database; a migrated one keeps it nullable only while legacy
-- rows without a readable request remain.
DO $$ DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM jobs WHERE request_enc IS NULL;
  IF n = 0 THEN
    ALTER TABLE jobs ALTER COLUMN request_enc SET NOT NULL;
  ELSE
    RAISE NOTICE 'jobs.request_enc stays nullable: % legacy row(s) predate encryption', n;
  END IF;
END $$;
