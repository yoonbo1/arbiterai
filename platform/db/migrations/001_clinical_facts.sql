-- Structured clinical facts extracted from de-identified page text (see docs/FEATURES_ROADMAP.md §2).
-- Text in this table is DE-IDENTIFIED: names/dates/etc. appear as <PERSON_1>-style tokens that are
-- restored only at query time, for the caller, from phi_tokens.
CREATE TABLE IF NOT EXISTS clinical_facts (
  id           bigserial PRIMARY KEY,
  tenant_id    uuid NOT NULL,
  patient_id   uuid NOT NULL,
  document_id  uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_id     bigint REFERENCES chunks(id) ON DELETE SET NULL,   -- citation target
  page         int  NOT NULL,
  section      text,                                              -- Medications, Plan, Diagnoses, ...
  kind         text NOT NULL CHECK (kind IN ('problem','medication','lab','vital','procedure',
                                             'allergy','immunization','referral','plan','other')),
  text         text NOT NULL,                                     -- span as written (de-identified)
  normalized   text NOT NULL,                                     -- lower-cased canonical form
  attributes   jsonb NOT NULL DEFAULT '{}'::jsonb,                -- dose, route, frequency, value, unit, ...
  assertion    text NOT NULL DEFAULT 'present'
               CHECK (assertion IN ('present','absent','possible','conditional','historical','family')),
  date_token   text,                                              -- nearest <DATE_TIME_n>, restorable per document
  code_system  text,                                              -- ICD10CM | RXNORM | LOINC | SNOMEDCT
  code         text,
  confidence   real NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
  extractor    text NOT NULL,                                     -- rules | ner | llm
  span_start   int,                                               -- offsets into the page text
  span_end     int,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS clinical_facts_lookup ON clinical_facts (tenant_id, patient_id, kind, normalized);
CREATE INDEX IF NOT EXISTS clinical_facts_doc    ON clinical_facts (document_id);

ALTER TABLE clinical_facts ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'clinical_facts' AND policyname = 'tenant_isolation') THEN
    CREATE POLICY tenant_isolation ON clinical_facts
      USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
      WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
  END IF;
END $$;

-- app_rw: read/write facts; DELETE so re-ingest can replace a document's facts.
GRANT SELECT, INSERT, UPDATE, DELETE ON clinical_facts TO app_rw;
GRANT USAGE ON SEQUENCE clinical_facts_id_seq TO app_rw;
