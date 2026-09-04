-- Page-relative character offsets for chunks, so a clinical fact (span_start/span_end on the page)
-- can be attached to the chunk that contains it (its citation target). Idempotent.
ALTER TABLE chunks
  ADD COLUMN IF NOT EXISTS char_start int,
  ADD COLUMN IF NOT EXISTS char_end   int;
CREATE INDEX IF NOT EXISTS clinical_facts_chunk ON clinical_facts (chunk_id);
