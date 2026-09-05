-- documents (TODO item 10, parts 2 and 3).
--
-- content_hash was md5(storage_uri): a hash of the client's path, which could neither dedupe nor
-- verify anything. It is now the SHA-256 (hex) of the file bytes, computed by the worker when it
-- first reads the file and before the row exists (worker/main.py), so UNIQUE (tenant_id,
-- content_hash) means "the same bytes are one document". The column keeps its type; only its
-- meaning changes. Legacy rows went with the legacy patient rows in 005.
--
-- storage_uri becomes nullable: a failed ingest now clears it and the failure is recorded on the
-- job (jobs.result_enc), so a rejected client-supplied path never stays behind in documents.
-- Idempotent.
ALTER TABLE documents ALTER COLUMN storage_uri DROP NOT NULL;
COMMENT ON COLUMN documents.content_hash IS 'sha256 (hex) of the file bytes; computed by the worker before the row is inserted';
COMMENT ON COLUMN documents.storage_uri  IS 'path in the tenant''s encrypted object store; NULL after a failed ingest';
