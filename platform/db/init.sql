-- HIPAA-oriented schema. Every PHI-bearing table carries tenant_id and is
-- protected by row-level security so the database itself enforces isolation.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------- Tenancy & access ----------
CREATE TABLE tenants (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL,
  isolation     text NOT NULL DEFAULT 'row' CHECK (isolation IN ('row','schema','dedicated')),
  baa_signed_at timestamptz,                      -- no BAA, no PHI
  status        text NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','offboarding')),
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE api_keys (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL REFERENCES tenants(id),
  key_prefix    text NOT NULL,                     -- first 12 chars, for display/log matching
  key_hash      text NOT NULL UNIQUE,              -- sha256(pepper || key); plaintext never stored
  scopes        text[] NOT NULL DEFAULT '{query}', -- ingest | query | cohort | admin
  rate_limit_per_min int NOT NULL DEFAULT 60,
  expires_at    timestamptz,
  revoked_at    timestamptz,
  last_used_at  timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON api_keys(tenant_id);

-- ---------- PHI-bearing tables ----------
CREATE TABLE patients (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants(id),
  external_id text NOT NULL,                       -- tenant's MRN; stored encrypted at rest
  cluster_id  int,                                 -- cohort assignment, recomputed offline
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, external_id)
);

CREATE TABLE documents (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenants(id),
  patient_id   uuid NOT NULL REFERENCES patients(id),
  doc_type     text,                               -- discharge_summary, radiology, lab, ...
  storage_uri  text NOT NULL,                      -- encrypted object store path
  content_hash text NOT NULL,                      -- dedupe / embedding cache key
  status       text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','indexed','failed')),
  pages        int,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, content_hash)
);

CREATE TABLE chunks (
  id          bigserial PRIMARY KEY,
  tenant_id   uuid NOT NULL,
  patient_id  uuid NOT NULL,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page        int,
  section     text,
  text        text NOT NULL,                       -- DE-IDENTIFIED text only
  embedding   vector(384) NOT NULL,                -- bge-small; change dim if model changes
  extraction  text NOT NULL CHECK (extraction IN ('text','ocr','vlm'))
);
CREATE INDEX ON chunks (tenant_id, patient_id);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);

-- Reversible de-identification map. Lives here, NEVER in the vector store.
CREATE TABLE phi_tokens (
  tenant_id   uuid NOT NULL,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  token       text NOT NULL,                       -- e.g. <PERSON_3>
  entity_type text NOT NULL,
  value_enc   bytea NOT NULL,                      -- pgp_sym_encrypt(value, tenant key)
  PRIMARY KEY (document_id, token)
);

CREATE TABLE jobs (
  id            uuid PRIMARY KEY,
  tenant_id     uuid NOT NULL,
  api_key_id    uuid NOT NULL,
  kind          text NOT NULL CHECK (kind IN ('ingest','query','cohort')),
  status        text NOT NULL DEFAULT 'queued',
  request       jsonb NOT NULL,                    -- de-identified before persisting
  result        jsonb,
  tokens_small  int DEFAULT 0,
  tokens_large  int DEFAULT 0,
  cost_cents    numeric(10,4) DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz
);
CREATE INDEX ON jobs (tenant_id, created_at DESC);

-- ---------- Audit (append-only) ----------
CREATE TABLE audit_log (
  id          bigserial PRIMARY KEY,
  ts          timestamptz NOT NULL DEFAULT now(),
  tenant_id   uuid,
  api_key_id  uuid,
  job_id      uuid,
  actor       text NOT NULL,                       -- key prefix or 'system'
  action      text NOT NULL,                       -- key.created, doc.ingested, phi.accessed ...
  patient_id  uuid,
  detail      jsonb
);
REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;

-- ---------- Row-level security ----------
-- App sets: SET LOCAL app.tenant_id = '<uuid>' at the start of each transaction.
ALTER TABLE patients   ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents  ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks     ENABLE ROW LEVEL SECURITY;
ALTER TABLE phi_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs       ENABLE ROW LEVEL SECURITY;

DO $$ DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['patients','documents','chunks','phi_tokens','jobs'] LOOP
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.tenant_id'', true)::uuid)
       WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true)::uuid)', t);
  END LOOP;
END $$;

-- Application role runs under RLS; migrations use the owner role (which bypasses RLS,
-- so the gateway/worker must never connect as it). The password is set from the
-- environment by db/02_app_role.sh (init .sql files get no env substitution); until
-- then the role cannot log in.
CREATE ROLE app_rw LOGIN;
GRANT USAGE ON SCHEMA public TO app_rw;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO app_rw;
-- Re-ingest of the same document replaces its derived rows.
GRANT DELETE ON chunks, phi_tokens TO app_rw;
-- audit_log is append-only for the application role (the blanket grant above included UPDATE).
REVOKE UPDATE, DELETE ON audit_log FROM app_rw;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_rw;
-- No CREATE on schema public: the app never creates tables. The optional LangGraph
-- postgres checkpointer uses DATABASE_ADMIN_URL (owner role) instead.
