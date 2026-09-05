# Changelog

All changes from the original two zips (`hipaa-doc-ai.zip`, `arbiterai-site.zip`), with the
reason for each. Dates are when the change was made.

## 2026-09-05 — platform hardening

### Platform — de-identification

- **Custom recognizers moved into `worker/recognizers/`** (TODO item 12, module part). One
  module per recognizer or result filter: `mrn.py`, `phone.py`, `clinician_name.py`,
  `address.py`, `date_filter.py`, `person_trim.py`, each with presidio-analyzer as its only
  dependency (no `worker.*` imports, enforced by a test) and a docstring carrying the failure,
  the scores and the examples from this changelog. `recognizers.custom_recognizers()` returns
  them in the order `deid.py` always registered them. Behaviour was checked byte-identical
  before anything else changed: the suite passed with the tests untouched (130 passed,
  2 skipped, 2 xfailed) and every pattern regex, score, name, entity, context list, the date
  regex and the title/label sets compared equal to the pre-move source. Eleven recognizer
  tests (20 cases) moved from `tests/test_deid.py` to the new `tests/test_recognizers.py`
  with no assertion dropped; `test_deid.py` keeps the engine, Scrubber, `_select`, `restore`
  and `contains_phi` tests. The four upstream PRs are written up in
  `platform/docs/UPSTREAM.md` (title, description, source module, target path in Presidio
  2.2.364, tests, what still needs adapting) and are **not opened**.
- **OCR-tolerant MRN labels close the 0.992 gap** (TODO item 14). The MRN recognizer is now
  `MrnRecognizer(PatternRecognizer)`, named `mrn_regex`, with three tiers: the exact label at
  0.85 as before; every edit-distance-1 variant of the label (one letter substituted or
  deleted: `MAN`, `MRM`, `RN`) and every spacing variant (`M R N`) at 0.7, generated from the
  label list (81 variants for `MRN`) and grouped by width so each lookbehind stays
  fixed-width; and a 0.5 fallback for a bare 6-10 digit run on a line that also carries a
  demographics cue (`DOB`, `Patient`, `Name`, `Sex`, `Age`). `MAN: 1234567`, `MRM 1234567`,
  `M R N: 1234567` and `Patient: John Doe   1234567   DOB 01/02/1960` are now scrubbed, the
  label kept; `03/05/2024`, `555-0100`, `75001`, `WBC 11000` and `HbA1c 9.0` on the same
  line are not (none has six consecutive digits). Known cost: a six-digit lab value written
  on the demographics line (`platelets 250000`) would be taken; the protect pass (item 13) is
  the fix for that. The OCR eval was not re-run here; the survivor it reported is now caught
  by the unit tests, so the expectation is 1.000.
- **The output leak check now counts dates and addresses** (TODO item 11). `contains_phi`
  ignored DATE_TIME and LOCATION entirely, so a raw date or address in an answer passed. It
  now applies the scrub's own criteria: a DATE_TIME hit counts when calendar-like
  (`date_filter`), a LOCATION hit when the address recognizer produced it, and the address
  patterns are also run directly on the text because Presidio drops a pattern hit that lies
  inside a same-typed, higher-scoring NER span. Bare state names (`Texas`), dosing frequencies
  and durations still pass. Rationale (validation runs before re-identification, so a raw
  date or address can only be a chunk the de-identifier missed) is in
  `platform/docs/HIPAA_CONTROLS.md`, "Output leak check". Found by the spot-check: the check
  also rejected every answer shaped `Attending: Dr. <PERSON_2> ...`, because the
  title-anchored name recognizer matches the bare `Dr` after `Attending:` and the leak check
  never applied the title trim the scrub applies (pre-existing; the pre-move code did the
  same). PERSON hits now go through `person_trim` too, so a bare title is not a leak but
  `Attending: Dr. Young` still is.
- **Tests: 180 passed, 2 skipped, 2 xfailed** (from 130). `test_recognizers.py` 58 cases:
  the 20 moved, plus package shape and isolation, per-recognizer spans and scores without the
  NLP engine, the 14 date-filter boundary cases, and the OCR-label and demographics-line
  cases with their negatives. `test_deid.py` 33 cases; a 13-case leak-check table replaces
  the old "ignores dates and locations" test. Still to do outside this change:
  `site/pages_blog.py` names `_address_recognizer()` in `worker/deid.py`; it is now
  `worker/recognizers/address.py`.

### Platform — query path

- **Integration fix after the merge.** The query-path change first carried its own copy of the
  job-finishing `UPDATE jobs ... result=` statement, written against the pre-encryption schema;
  merged with the data-at-rest change (`result_enc` under the tenant key) it failed on every
  query with `UndefinedColumn`, which the 20-record eval showed as 40 of 40 validation failures
  with zero tokens. `store.audit` now takes an optional `action`/`detail` and is the single
  writer for both paths; `graph.audit` passes the query outcome. Caught by the eval, not the
  unit tests: the fake connection accepted any SQL. Lesson kept in `TODO.md` (dev-box hygiene):
  a schema test that executes the worker's statements against a throwaway Postgres.

- **The audit trail now says whether an answer was delivered** (TODO item 7). The audit
  node in `worker/graph.py` wrote `job.query.completed` for every finished query, including
  the ones validation rejected. A rejected query now writes `job.query.rejected`; only a
  delivered answer writes `job.query.completed`. Both carry the same `detail`: `reasons`
  (the failed checks among `phi_leak`, `cites_chunks`, `grounded`, or `no_chunks`), the
  three check results and the faithfulness score, `attempts`, `escalated`,
  `escalation_skipped`, `tokens_restored`, `chunks_read`, `phi_reidentified`; never answer
  text. The job row is unchanged (`failed`, empty answer, `errors: ["validation_failed"]`,
  as the gateway and `eval/run_eval.py` already read it). `job.ingest.completed` is
  untouched. Because `store.audit` hard-codes `job.<kind>.completed` and `store.py` was
  frozen for this change, the query path writes its own job row and audit row from
  `graph.py` (`query_outcome`, `_write_query_audit`); folding an `action`/`detail` argument
  into `store.audit` later would remove the duplicated `UPDATE jobs`.
- **Escalation is skipped when the tiers are identical** (TODO item 9, post-mortem 3).
  `LARGE_MODEL_URL` / `LARGE_MODEL` fall back to `SMALL_MODEL_URL` / `SMALL_MODEL` when
  unset, which on this machine meant a failed draft was regenerated by the same model at
  temperature 0, metered at the large-tier rate, with the same verdict. `llm.tiers_identical()`
  compares the resolved (endpoint, model) pairs; when they are equal, `validate` records
  `escalation_skipped: "large tier identical to small tier"` in the validation dict
  (persisted in `jobs.result`) and the query fails at one attempt, so `queries_escalated`
  in the eval (attempts > 1) does not count it. Escalation works as before when the tiers
  differ; the rule and the variables are documented in `worker/llm.py`.
- **"At most one escalation" is an explicit guard.** `MAX_ESCALATIONS = 1`, `may_escalate()`
  is the single routing decision (`after_validate` only asks it), and `generate` raises
  `EscalationLimitExceeded` before any model call rather than run a third generation.
- **Tests.** `tests/test_graph_query.py` (10 new): delivered answer → `job.query.completed`;
  failed validation with differing tiers → exactly one escalation, then `job.query.rejected`
  with the reasons; identical tiers → no escalation, `escalation_skipped`, rejected at one
  attempt; a PHI leak as a rejection reason that is never retried; `no_chunks` → rejected;
  ingest still through `store.audit`; the guard in routing and in `generate`; the tier rule.
  The graph runs end to end through `build_query()`; `langgraph` and `pytesseract` are
  stubbed only while `worker.graph` is imported and only when the host venv lacks them (CI
  installs both), so `test_annotate.py`'s langgraph skip is unchanged. Suite: 130 → 140
  passed, 2 skipped, 2 xfailed.

### Platform — data at rest

Three gaps a reader of `db/init.sql` would have caught, closed and probed against the live
stack (TODO items 6, 8, 10). Migrations `003`–`006` apply to an existing database with
`make migrate` and are no-ops on a fresh one; the second run is a no-op on both.

- **`audit_log` under row-level security** (`db/init.sql`, `db/migrations/003_audit_log_rls.sql`).
  The table was append-only but `app_rw` could `SELECT` every tenant's rows. It now carries the
  same `tenant_isolation` policy as the PHI tables (`USING` and `WITH CHECK` on
  `app.tenant_id`) and `tenant_id` is `NOT NULL`: every row belongs to a tenant. Every writer
  was traced: the gateway's job submit and facts read and the worker's job completion already
  ran with the tenant set; the two admin inserts (`key.created`, `key.revoked`) ran on the bare
  pool with no tenant and would have failed the policy, so they now run in a transaction with
  `app.tenant_id` set to the tenant the key belongs to (the tenant can read its own key
  lifecycle). Decision: no tenant-less rows, so no NULL-tenant policy; a system event with no
  tenant goes to the service logs. The `REVOKE UPDATE, DELETE` stays. Probed as `app_rw`
  with `app.tenant_id = A`: 0 of B's 8 rows visible, all 988 of A's; `INSERT` for B → "new row
  violates row-level security policy"; `UPDATE`/`DELETE` → permission denied.
- **Job payloads encrypted** (`db/migrations/004_jobs_encrypt.sql`, `gateway/main.py`,
  `worker/store.py`, `worker/main.py`). `jobs.request` held the raw question and patient
  external id before de-identification and `jobs.result` the re-identified answer, both
  plaintext `jsonb` despite the schema comment. Both columns are gone; `request_enc` and
  `result_enc` are `bytea` from `pgp_sym_encrypt` under the tenant key, the key already used
  for `phi_tokens.value_enc`. The gateway encrypts on submit and decrypts the result only for
  `GET /v1/jobs/{id}`, for the key RLS has already matched to the job; the worker decrypts
  the request in `store.get_job` and encrypts the result and any failure reason. The eval
  harness now counts escalations from the API response instead of reading `result` from the
  table. Legacy dev rows were not re-encrypted (psql has no key; synthetic data only); the
  migration says so and leaves `request_enc` nullable while such rows remain.
- **One key derivation for both services** (`worker/tenant_keys.py`, new). The worker derived
  the tenant key in a private `store._tenant_key`; the gateway now needs the same key, so the
  derivation (`TENANT_KEK + tenant_id`, unchanged) moved to a standard-library-only module both
  import. The gateway image is built from `platform/` (`docker-compose.yml`
  `build: { context: ., dockerfile: gateway/Dockerfile }`) so it can copy that one file;
  `platform/.dockerignore` sends nothing else (`.env`, `data/` never enter the context).
  `tests/test_tenant_keys.py` pins that both services import the module rather than a copy.
- **Patient external id hashed and encrypted** (`db/migrations/005_patients_external_id.sql`).
  `patients.external_id` (an MRN) was plaintext. Replaced by `external_id_hash`, an HMAC-SHA256
  under a key derived from the tenant key (domain-separated, so the same MRN hashes differently
  per tenant and a dump cannot be joined to a list of MRNs), used by every lookup (ingest,
  query, `GET /v1/patients/{id}/facts`, the extraction eval), and `external_id_enc`
  (`pgp_sym_encrypt`), decrypted only to hand the id back to the caller that presented it.
  The dev rows could not be converted without the key, so the migration drops the legacy
  patient rows and their documents (synthetic) and `make eval` re-ingests; a real deployment
  would backfill from a process holding the key. `eval/run_extraction_eval.py` reads
  `TENANT_KEK` from the environment or `platform/.env` to hash the manifest ids.
- **`content_hash` is a hash of the bytes**
  (`db/migrations/006_documents_hash_and_failed_ingest.sql`, `worker/main.py`,
  `store.sha256_file` / `store.upsert_document`). It was `md5(storage_uri)`. The worker now
  hashes the file before any row exists, so `UNIQUE (tenant_id, content_hash)` means "the same
  bytes are one document": a re-ingest or a retry after a failure reuses the row; new bytes at a
  known path are a new version of that document and reuse its row too. Verified: the stored
  value equals `shasum -a 256` of the file on the host.
- **A failed ingest leaves no client-supplied path behind.** `documents.storage_uri` is
  nullable; on failure the row is marked `failed` with `storage_uri = NULL` and the reason is
  recorded on the job (`result_enc`). A path outside `DATA_ROOT` now fails before any row
  exists (no patient, no document). Probed: `/etc/passwd` → job `failed`
  `{"error": "PermissionError"}`, no `documents` row; a zero-byte file → `EmptyFileError`,
  row `failed` with `storage_uri NULL`.
- **Tests** (`tests/test_tenant_keys.py`, `test_gateway_jobs.py`, `test_store.py`,
  `test_schema.py`; `test_gateway_facts.py` updated): 167 passed, 2 skipped, 2 xfailed
  (was 130). `test_schema.py` reads `init.sql` and the migrations: no plaintext
  `request`/`result`/`external_id` column, `audit_log` in the policy list, and no SQL literal
  in the services names an old column.
- **End to end after migrating and rebuilding**, `make eval LIMIT=3`: 3 documents, 6 queries,
  accuracy 1.0, 0 cross-patient leaks, 0 validation failures, p50 3.6 s. Whole-string de-id
  recall 0.944 = the one known survivor (P00001's scan, where Tesseract reads `MRN:` as `MAN:`;
  TODO item 14, unchanged by this work). `GET /v1/jobs/{id}`: 200 with the decrypted answer
  for the owning key, 404 for key B; the facts endpoint: 200 and the decrypted id for key A,
  404 for key B.
- **Docs.** `docs/HIPAA_CONTROLS.md` rows for audit controls, integrity and encryption at rest;
  README invariants table (audit-log row); `.env.example` says what `TENANT_KEK` now covers.


## 2026-09-04 — repositioning: open reference implementation

Per `ARBITER_REPOSITIONING.md`: the site, README and blog now describe Arbiter as an open
reference implementation of HIPAA-safe document AI built by one engineer, not a product.

### Site

- **Removed.** `pricing.html` and every link to it; the deployment tiers; SLA, uptime,
  named-support, onsite and "we install, you operate" copy; "Request a demo", "Contact
  sales", "Start a pilot" and the `?plan=` variants; the "How a pilot works" section; the
  BAA promise; the shared-responsibility table and the attestations block; the contact form
  and its `/submit` handler (`wsgi.py` no longer needs `FORM_ENDPOINT`); the mock
  chain-of-custody ledger (job `7f3a…c21e`, tenant `northgate-clinic`). Reason: a solo
  project cannot honestly offer any of it, and the technical readers the site is for notice.
- **Renamed.** `product.html` → `how-it-works.html` (architecture explainer: each stage
  with what it does, where it lives in the repo, and which eval or test covers it);
  `security.html` is now "Security model" (five numbered invariants, each with its
  enforcement point and its test, the superuser/RLS finding in plain words, and the honest
  scope statement verbatim). `wsgi.py` 301s the old paths (`/product.html` →
  `/how-it-works.html`, `/pricing.html` → `/`).
- **Home.** H1 "Clinical document AI you can audit.", the one-liner, the four properties
  linked to code and tests, the six use cases the implementation covers, a benchmarks table
  with the dataset labelled on every row (synthetic marked; i2b2 2014 "not yet run"), four
  "failure modes I found" cards linking to the post-mortems, an author strip, and a real
  trace from the eval harness (synthetic record P00001) in place of the mock ledger.
- **Docs.** Now the primary page: "Run it locally", "Run the evals" (what each metric
  means, how to add gold questions), "Data" (all shipped records are synthetic; how to point
  the harness at i2b2 2014), then the API.
- **About / contact.** Author, why, what it is not; email and GitHub profile. No form.
- **Global.** Nav: How it works · Security model · Docs · Blog · About. Footer: Architecture
  · Security model · Evals · Blog · Contact, "© 2026 Yoonbo Cho", disclaimer kept. Titles,
  meta, og and twitter descriptions carry the short form; the home page og:description
  carries the full one-liner. First person singular throughout; "we" removed. No GitHub
  repo link until the repo is public, and never "open-source" until then.
- **Blog.** Four post-mortems, each ≤ 1,500 words, numbers from this changelog, code and
  tests named by path: spaCy redacting "daily"; the flattering 0.967 recall; the 7B judge
  and citation placement; the services connecting as the Postgres superuser.

### Repository

- **`README.md`** restructured per the brief: one-liner, architecture diagram, invariants
  with enforcement and tests, quickstart, eval results table, failure modes, what it is
  not, author. No licence yet and the repo stays private; both are the owner's call and
  sit in the needs-you table in `TODO.md`.
- **`TODO.md`** needs-you table: dropped the form endpoint row (no form), marked the apex
  forwarding done (it activated 2026-09-04 and the apex 301s to www), added repo
  visibility and licence, LinkedIn URL, Search Console, and the i2b2 2014 run.

## 2026-09-03 — first end-to-end bring-up

### Repository

- **Monorepo layout.** `platform/` = product, `site/` = marketing site, both unchanged in
  structure from the zips. Added top-level `README.md`, `Makefile`, `CHANGELOG.md`, `TODO.md`.
- **`.gitignore`.** Ignores `.env` and `.env.*` (except `.env.example`), `data/`,
  `site/public/` (generated), `.venv/`, the source zips, and OS/editor noise. Reason: the
  founder's constraint that `.env` and data never get committed; `public/` is a build artifact
  regenerated by `build.py` on the host.
- **`git init` on `main`.** No commits are made by the tooling; the founder commits.
- **Host tooling.** The machine had no container runtime. Installed Colima + Docker CLI +
  Compose + buildx via Homebrew (`colima start --cpu 6 --memory 12 --disk 80 --vm-type vz
  --vz-rosetta`). Reason: `docker compose` was required and nothing else was installed.
  Rosetta lets amd64-only images run (slowly) on Apple Silicon.
- **Python 3.12 venv at `.venv/`.** Python on PATH is 3.14, which several scientific
  dependencies (spaCy, Presidio) do not yet support. `make venv` recreates it.

### Makefile

- `make site`, `make up`, `make down`, `make synth`, `make eval`, `make test` as requested,
  plus `make venv`, `make ps`, `make logs`, `make bootstrap`, `make llm`, `make down-v`, `make clean`.

### site/

- **`assets/styles.css`: `.grid-2>*,.grid-3>*{min-width:0}`.** Grid items default to
  `min-width:auto`, so the long code lines in the product page's Integration `<pre>` blocks
  widened the grid track to 627 px and made the page 651 px wide on a 375 px phone (and pushed
  the second `<pre>` past the wrap on desktop). With `min-width:0` the `<pre>`'s own
  `overflow-x:auto` scrolls instead. Found by checking every page at 375×812.
- **`assets/og-image.png` (new, 1200×630, 55 KB).** Generated with Pillow from the palette in
  `styles.css` (ink background, frost wordmark, brass crossbar and rule, verdigris dot, muted
  tagline). The shell template already referenced `/assets/og-image.png` on every page; it
  was the only broken reference in the link check.
- **QA results (no change needed).** 280 internal references across 10 pages resolve,
  including `/security.html#baa`. No console errors or failed same-origin requests on any page
  at desktop or mobile. Nav toggle, ledger animation, footer year, and contact form render
  correctly. Polish recommendations are in the bring-up report and `TODO.md`.
- **`.claude/launch.json` (new, repo root).** Preview-server config used to serve
  `site/public/` on port 8765 for the browser checks.

### platform/ — what broke on first execution and what changed

The code had never been run. Bringing it up on this machine (Apple M4, no NVIDIA GPU,
Docker via Colima) surfaced the following. Every item was verified by running the stack.

**Runtime that would have failed on any machine**

- **`worker/store.py`: `Connection.executemany` does not exist in psycopg 3.** Every ingest
  crashed at `chunk_embed`. Inserts now go through a cursor. Also: lazy `get_pool()` so the
  module imports without a database (tests), `Jsonb` adapters, explicit `::vector` literal
  with a 384-dim guard, re-ingest deletes the document's old chunks and PHI tokens first,
  `TENANT_KEK` is required (the silent `dev-only-key` fallback is gone).
- **`gateway/main.py`: `jobs.result` came back as a JSON string.** asyncpg does not decode
  `jsonb` by default, so `eval/run_eval.py` would have crashed on `.get()`. The pool now
  registers json/jsonb codecs. Also: client-supplied ids are validated as UUIDs (404 instead
  of 500), `/healthz` really checks Postgres and Redis (503 otherwise) so the compose
  healthcheck means something, request-model bounds, exact version pins.
- **LangGraph checkpointer could not serialize the state.** `State.pages` held PIL images.
  `extract.Page` now carries PNG bytes and builds the image on demand. The checkpointer is
  selectable with `CHECKPOINTER=none|memory|postgres`, default `none`: `postgres` would
  persist pre-de-identification text and the plaintext PHI map outside RLS, and `memory`
  grows without bound in a long-running worker.
- **`graph.deidentify` split pages on `"\n\n"`,** which page text also contains, so
  page/text alignment silently drifted. De-identification is now per page with shared token
  state (`deid.scrub_pages`), page count asserted.
- **`worker/main.py` consumer loop.** Re-ingesting the same document produced a dangling
  `document_id` (FK failure); now `ON CONFLICT (tenant_id, content_hash) DO UPDATE ... RETURNING id`.
  Jobs invisible under RLS crashed the loop; now logged and acked. Messages left pending by
  a dead worker were never reclaimed; an XAUTOCLAIM pass runs before every read
  (`WORKER_CLAIM_IDLE_MS`) with a delivery cap (`WORKER_MAX_DELIVERIES`, then mark failed
  and ack). The exception branch itself could raise and kill the process; wrapped. SIGTERM
  finishes the current job and exits (`stop_grace_period: 60s`). Verified by killing a
  worker mid-job and by leaving a message pending under a ghost consumer.
- **`worker/deid.py`.** The MRN recognizer scored 0.4 against a 0.5 threshold, so MRNs were
  never scrubbed; rewritten (labelled `MRN: 1234567` scores 0.85, only the digits are
  replaced). Presidio missed NANP phone numbers with extensions; added a regex recognizer.
  Overlapping spans are resolved (higher score, then longer) instead of corrupting text.
  spaCy model is configurable via `SPACY_MODEL` through `NlpEngineProvider` (tests use
  `en_core_web_sm` on the host). Citation markers like `[12]` are stripped before the leak check.
- **`worker/llm.py`.** The large tier defaulted to the VLM URL, which is empty here; it now
  falls back to the small tier. The faithfulness judge prompt scored a fully supported
  answer 0.5 on qwen2.5:7b (below the 0.7 gate); rewritten and measured (supported 1.0,
  unsupported 0.0). Missing `usage` in a response is tolerated.
- **`worker/extract.py`.** With `VLM_URL` empty the router never returns `vlm`; it routes
  `ocr` and flags `vlm_wanted` so usage stays honest. `storage_uri` is client input and was
  opened as-is; it is now confined to `DATA_ROOT` after symlink resolution (a `/etc/passwd`
  probe fails the job cleanly). Tesseract float confidences handled.
- **`worker/graph.py`.** A `no_chunks` branch after retrieval avoids model calls when the
  patient has nothing indexed; validation records `faithfulness` and `attempts`.
- **`worker/retrieval.py`.** BM25 guard for empty token lists; shared vector literal helper.

**Isolation that was only nominal**

- **RLS did not apply.** Gateway and worker connected as the Postgres superuser, which
  bypasses row-level security, so "other tenants' jobs return 404 via RLS" was false.
  The app now connects as `app_rw`; its password comes from `PG_APP_PASSWORD` via
  `db/02_app_role.sh` (init `.sql` files get no environment substitution, `.sh` files do),
  so the hard-coded password in `init.sql` is gone. `app_rw` gets DELETE on chunks and
  phi_tokens (re-ingest) and loses UPDATE/DELETE on `audit_log` (the blanket grant had
  given it UPDATE, defeating append-only). Proven: key B gets 404 on tenant A's job, an
  `app_rw` session with `app.tenant_id = A` sees zero rows of B, and inserting a row for B
  while set to A violates the policy.

**Dependencies and images**

- **`worker/requirements.txt`.** spaCy 3.7 wheels are built against numpy 1 and break under
  numpy 2 on `python:3.12-slim`; pinned spaCy 3.8.16 / thinc 8.3.13 / numpy 2.4.6 with
  presidio-analyzer 2.2.364, langgraph 0.2.76, langchain-core 0.3.86, psycopg 3.2.13,
  pymupdf 1.24.14. Dropped `langchain-openai` and `presidio-anonymizer` (never imported).
  `Dockerfile` takes `ARG SPACY_MODEL` (default `en_core_web_lg`, 560 MB) so a dev build
  can use `en_core_web_sm`.
- **Embeddings service replaced.** `text-embeddings-inference:cpu-*` images are
  linux/amd64 only; under Rosetta cpu-1.5 crashed and cpu-1.7 never finished warming up.
  New `platform/embeddings/` (FastAPI + fastembed/ONNX, `BAAI/bge-small-en-v1.5`, 384 dims)
  exposes the same `POST /embed` and `GET /health`; `store.embed()` is unchanged. The TEI
  image remains as a commented alternative for amd64 hosts.
- **`docker-compose.yml`.** vLLM services moved behind the `gpu` profile (`vllm-vlm` also
  keeps `vlm`), so the default `up` starts exactly postgres, redis, embeddings, gateway,
  worker. Healthchecks on all of them, `depends_on: condition: service_healthy`,
  `restart: unless-stopped`, `extra_hosts` so the worker reaches Ollama on the host,
  `PG_HOST_PORT` because this Mac already runs a Homebrew Postgres on 5432. Ports stay on
  127.0.0.1.
- **Language model.** No CUDA GPU, so Ollama (Homebrew formula, not a service) serves
  `qwen2.5:7b-instruct` on the host with Metal; containers use
  `http://host.docker.internal:11434/v1` for both tiers. Binding Ollama to `0.0.0.0` is
  needed for the VM to reach it and is dev-only (LAN exposure).

**Scripts, eval, docs**

- **`scripts/bootstrap_tenant.sh`.** No longer `source`s the whole `.env` (breaks on
  metacharacters); reads only `ADMIN_TOKEN`, works from any directory, prints
  `tenant_id=` and `api_key=` plainly.
- **`eval/run_eval.py`.** p95 index safe for any n; refuses to run as a superuser or
  BYPASSRLS role so the de-id/leak check is meaningful; HTTP timeouts and status checks.
- **`.env.example`.** Every variable documented with placeholders only; new: `PG_APP_*`,
  `PG_HOST_PORT`, `DATABASE_ADMIN_URL`, `LARGE_MODEL_URL/LARGE_MODEL`, `LLM_TIMEOUT_S`,
  `EMBED_MODEL`, `CHECKPOINTER`, `SPACY_MODEL`, `DATA_ROOT`, `WORKER_MAX_DELIVERIES`,
  `WORKER_CLAIM_IDLE_MS`, `WORKER_DEBUG_TRACEBACKS`.
- **`README.md`.** Quick start rewritten for the default profile, Ollama on Apple Silicon,
  and the `make` targets. The advice to point `VLM_URL` at the small text model was wrong
  (it would have sent page images to a text model) and was removed. `docs/*.md` untouched.
- **`tests/`, `requirements-dev.txt`.** Pytest coverage for `gateway/auth.py`,
  `worker/deid.py` (real Presidio with `en_core_web_sm`), `worker/retrieval.py` (store
  faked). See the test section below.

### platform/tests — pytest coverage (58 passed, 2 xfailed)

- **`tests/conftest.py`.** Sets `API_KEY_PEPPER`, `SPACY_MODEL=en_core_web_sm`, and dummy
  database/Redis/KEK values before any import; puts `platform/` and `platform/gateway` on
  `sys.path`; provides `FakeRedis` and `FakePool` fixtures. No Docker, no network.
- **`tests/test_auth.py` (13 tests).** Key shape, prefix, HMAC determinism and pepper
  rotation, DB-path resolve with the cache populated at 60 s, cache-hit path without a DB
  call, unknown/revoked keys, tampered plaintext, rate limit allow-N/reject-N+1 with a single
  90 s expiry, minute rollover, per-key buckets.
- **`tests/test_deid.py` (33 tests, real Presidio + `en_core_web_sm`).** Discharge-summary
  scrub leaves none of the injected strings, tokens are well formed, repeated names share a
  token, exact round trip through `restore`, `scrub_pages` keeps page count and shares tokens,
  labelled MRN and phone-with-extension forms, overlap resolution, leak check on tokens and
  citations vs raw identifiers. Two documented xfails: Presidio deliberately rejects the
  textbook fake SSN `123-45-6789`, and `en_core_web_sm` cannot find `SMITH, JOHN` after
  `PATIENT NAME:` (`en_core_web_lg` is the production model).
- **`tests/test_retrieval.py` (14 tests).** Tenant/patient hard filter checked in the SQL
  and bind parameters, pool size is the SQL LIMIT, BM25 lifts an exact drug-name match over a
  higher-similarity row, RRF scores recomputed independently, k limit, empty result, vector
  literal and 384-dim guard, embedding batch sizes.
- **`requirements-dev.txt`, `pytest.ini`.** Exact pytest/pytest-asyncio pins; `asyncio_mode=auto`.

### Bugs the tests found, fixed in source

- **`worker/deid.py`: leak check looser than the scrub.** `contains_phi` defaulted to
  threshold 0.6 while `scrub` used 0.5; Presidio scores a bare SSN 0.5, so the scrub redacted
  it but the output leak check let it through. Both now use 0.5.
- **`worker/retrieval.py`: BM25 was punctuation-blind.** Tokenizing with `str.split()` meant
  `ceftriaxone.` at a sentence end never matched the query term. Tokens are now `\w+` runs.
- **`worker/retrieval.py`: reciprocal rank fusion gave zero-overlap chunks a lexical bonus.**
  Every chunk received `1/(60+rank)` from the BM25 list even with a score of 0, so an exact
  term match could at best tie the top vector hit and lose on stable sort. Only chunks with a
  positive BM25 score are now in the BM25 list, which is how RRF is defined.

### Eval harness, first run (20 documents, 40 queries) and what it changed

First run of `eval/run_eval.py` after the bring-up, before the fixes below:

| metric | value |
|---|---|
| de-id recall (whole injected string) | 0.967 (116/120), gate is 0.99 |
| cross-patient leaks | 0 |
| answer accuracy (strict substring) | 0.575 (23/40) |
| p50 / p95 latency | 3.6 s / 5.1 s |
| wall time | 2 min 49 s |
| cost at placeholder rates | 0.50 cents for 60 jobs |

Drilling into the misses (all verified by re-issuing the exact prompts to the model):

- **The grounding judge rejected 5 correct answers.** `...is 9.0% [7].` scored 0.0 and
  `...is 9.0%. [7]` scored 1.0 on identical facts. Escalation re-ran the same model at
  temperature 0, got the same verdict, and discarded the answer at 8x the cost.
  **Fix (`worker/llm.py`):** citation markers are stripped before judging; the judge's
  tokens are now returned and metered in `graph.validate` (they were about half of all model
  traffic and unbilled).
- **"daily" and "nightly" were redacted as dates.** spaCy's DATE label covers frequencies
  and durations; `sertraline 50 mg <DATE_TIME_2>` destroyed the dosing instruction in the
  index and caused 11 of the 12 medication-list misses. **Fix (`worker/deid.py`):** a
  DATE_TIME hit is kept only if it contains something calendar-like (month name, numeric
  date, ISO date, year, ordinal). Safe Harbor dates are dates tied to a person, not
  frequencies.
- **The four surviving PHI strings were all `Dr. <common-word surname>`** (Fields, Lewis,
  Young, Holder) that spaCy NER missed. **Fix:** a title-anchored PERSON recognizer
  (`Dr.`, `Doctor`, `Attending:`, `Patient:`, `Name:` ...) that replaces only the name.
- **The whole-string recall metric was flattering.** Only the city of each address was
  tokenized; street lines survived in 7/20 documents and ZIP codes in 14/20, and the metric
  never noticed because it checks the full 40-character address. **Fixes:** a LOCATION
  recognizer for labelled `Address:` lines, USPS-suffix street lines, and ZIP codes
  (`worker/deid.py`); `eval/run_eval.py` now also reports `deid_recall_strict` (any surviving
  comma-separated component counts as a leak), `answer_accuracy_lenient` (drug + dose, or the
  lab value, for every gold item), `queries_failed_validation`, `queries_escalated`, and
  tokens / cost per query from the `jobs` table.
- **A bare 10-digit phone number after `Tel:`** was only caught because spaCy mislabelled it
  as a date; with the date filter it would have survived. Added a bare-NANP pattern to the
  phone recognizer that only clears the threshold when a phone-like word is nearby.

### Eval harness, second run (same 20 documents, after the fixes above)

| metric | run 1 | run 2 |
|---|---|---|
| de-id recall, whole string | 0.967 | **1.000** |
| de-id recall, strict per component (new) | not measured (about 0.81 by hand) | 0.9625 |
| cross-patient leaks | 0 | 0 |
| answer accuracy, strict | 0.575 | **0.95** |
| queries rejected by validation | 5 | 1 |
| escalations | 5 | 1 |
| p50 / p95 latency | 3.6 s / 5.1 s | 4.1 s / 5.1 s |
| tokens (small / large) | 13,055 / 1,586 | 24,969 / 297 |
| cost per query at placeholder rates | 0.012 c (judge calls unbilled) | 0.014 c (judge calls now metered) |

The six strict-metric survivors were all Faker-invented city names (`Blankenshipstad`,
`Hernandezview`, `Kingland`, `New Amber`, ...) that spaCy NER does not know. The two
answer misses were both Tesseract misreads on the synthetic scans that the model copied
faithfully (`HbAtc 7.2%`, which the judge then refused to ground, and `fisinopril`); those
need the vision route on a GPU box or a drug-name correction step (see `TODO.md`).
Token counts roughly doubled because the judge's calls are now counted; latency rose about
0.5 s per query for the same reason the tokens did not: nothing changed in the answer path.

**Third iteration (`worker/deid.py`).** Added a `City, ST 12345` pattern (no knowledge of
city names needed) and extended the labelled `Address:` pattern to take the whole
`street, city, ST ZIP` line, stopping at the next label on the line. Four new tests cover
the address line, an unlabelled city/state/ZIP, dosing frequencies surviving, and calendar
dates still being removed. Run 3 numbers are in the bring-up report.

**Run 3 (after the third iteration):** de-id recall 1.000 whole-string and **1.000 strict**,
0 cross-patient leaks, answer accuracy 0.95 (the same two Tesseract misreads), 1 validation
failure, 1 escalation, p50 4.1 s, p95 4.1 s, 0.013 cents per query. Wall time 2 min 49 s.

**Fourth iteration (`worker/deid.py`), from the new tests rather than the eval.**
- The labelled-address pattern could start at the space after `Address:` because the
  no-space lookbehind alternative matched one character earlier; the token value then carried
  a leading space. Fixed with a `(?=\S)` guard, and every span is now trimmed of edge
  whitespace before replacement.
- Overlap resolution changed from "keep the best span, drop the rest" to **merge overlapping
  candidates into their union** (typed by the highest-scoring member). With the old rule,
  when spaCy tagged only the city inside `Kingland, TX 75001`, Presidio first dropped the
  ZIP as a contained duplicate and the resolver then kept the shorter city span, leaving
  `TX 75001` in the index. For de-identification, a fragment of any above-threshold
  candidate must never survive, so union is the only safe policy.
- The title-anchored name pattern matched case-insensitively (Presidio compiles every
  pattern with IGNORECASE) and swallowed the following lowercase word
  (`Priya Raghunathan-Okafor reviewed`). Python's scoped `(?-i:...)` flag makes the name
  part case-sensitive.
- Test count is now 62 passed, 2 xfailed. Run 4 numbers are in the bring-up report.

**Run 4 (final code, same 20 documents):** de-id recall 1.000 whole-string and 1.000
strict, 0 cross-patient leaks, answer accuracy 0.95 (38/40; the two misses are the
Tesseract misreads), 1 validation failure, 1 escalation, p50 3.6 s, p95 4.1 s, 0.013 cents
per query at the placeholder rates, wall time 2 min 47 s. Outputs of all four runs are in
`platform/data/eval/` (git-ignored).

## 2026-09-03 — marketing site deployed to Heroku

- **`site/` gained a minimal Heroku target**: `Procfile`, `requirements.txt` (gunicorn,
  WhiteNoise), `.python-version`, `app.json`, `wsgi.py`, `bin/post_compile`. The site is
  static, so WhiteNoise serves `public/` and anything unmatched falls through to the
  generated `404.html`. `bin/post_compile` runs `build.py` during slug compilation because
  `public/` is generated and git-ignored.
- **Security headers moved into the app.** `_headers` is read only by Netlify and
  Cloudflare Pages, and `vercel.json` only by Vercel, so on Heroku the same policy is
  applied by `wsgi.py`. HSTS is set without `preload`, which is a one-way commitment.
- **`build.py` takes the canonical origin from `SITE_URL`.** It was hard-coded to
  `https://arbiterai.tech`, which would have advertised the wrong host from a preview
  deploy. The Heroku app sets `https://www.arbiterai.tech`.
- **`make serve-site` now uses gunicorn** instead of `python -m http.server`, so what runs
  locally is what runs in production, headers and 404 included. `make deploy-site` pushes
  the `site/` subtree. `.claude/launch.json` follows.
- **App `arbiterai-site` created in region us**, deployed from the `site/` subtree, all ten
  pages plus assets, sitemap and robots verified live. Automated Certificate Management is
  enabled and waiting on DNS.
- **Not done: the dyno is Basic, not Eco.** `heroku ps:type eco` is refused until the
  account holds an Eco subscription, which is a purchase to make in the dashboard.
- **Not done: DNS at Squarespace.** The Chrome profile is signed out of Squarespace, and I
  do not enter credentials. The records are in `site/README.md`.

## 2026-09-03 — arbiterai.tech live on Heroku

- **Squarespace DNS configured.** A `www` CNAME to the Heroku DNS target, and a domain
  forwarding rule sending the apex to `https://www.arbiterai.tech` as a permanent redirect
  with the path preserved.
- **Fixed a pre-existing broken forwarding rule.** It forwarded
  `arbiterai.tech.arbiterai.tech`, because the subdomain field appends the domain and the
  full domain had been typed into it. The root domain is entered as `@`. The rule was also
  a temporary redirect with paths dropped; it is now permanent with paths forwarded.
- **Correction to an earlier note.** Squarespace DNS does support `ALIAS`, so the apex could
  point at Heroku directly instead of forwarding. Documented in `site/README.md` as the
  alternative if the bare domain should become canonical.
- **TLS issued.** Let's Encrypt certificate for `www.arbiterai.tech` via Heroku ACM.
- **Verified live**: all ten pages, the stylesheet, script, OG image, sitemap and robots
  return 200; an unknown path returns the 404 page; all six security headers are present;
  the canonical URL is `https://www.arbiterai.tech/`; and `arbiterai.tech/docs.html`
  301-redirects to `www.arbiterai.tech/docs.html`.

## 2026-09-03 — contact form fixed, placeholder copy removed

- **The demo request form worked on no host.** It carried Netlify-only markup
  (`data-netlify="true"`, posting to a static page) and the site runs on Heroku, where a
  POST to a static path returns 405. Verified against production before the fix. Every
  submission was being lost.
  `wsgi.py` now handles `POST /submit`: honeypot check, required-field and email validation,
  then forwarding to `FORM_ENDPOINT`. Forwarding is server side, so the browser only talks
  to this origin and the content security policy needs no third-party `connect-src`.
  Works with JavaScript (fetch, no reload) and without it (303 back to
  `/contact.html?sent=1`). With `FORM_ENDPOINT` unset the submission is written to the
  application log, and the app warns about that at boot, so nothing is silently lost.
- **`main.js`**: reveals the thank-you panel when the page loads with `sent=1`, which the
  no-JavaScript round trip needs, and posts `URLSearchParams` rather than `FormData` so the
  body is form-encoded and the handler can parse it without a multipart parser. A failed
  submission now shows an error panel pointing at the mailbox instead of an alert box.
- **Placeholder copy removed from the live site**: the "replace with date" lines on privacy
  and terms now carry a real date; the "Replace with your jurisdiction" clause defers to the
  customer's signed agreement rather than naming a jurisdiction nobody has chosen; the
  "Founder and team bios go here" callout, the "Update this list as attestations are
  completed" note, and the Netlify how-to under the form are gone. All were notes to
  ourselves that shipped to visitors.
- **`styles.css`**: a `.form-error` panel matching the existing `.form-ok` panel.

## 2026-09-03 — apex domain investigation

- **Diagnosed why `arbiterai.tech` still showed Squarespace's parking page.** Deeper paths
  such as `/product.html` redirected to www correctly, but the root returned 200 from
  Squarespace with a cache `age` of nearly nine hours. Squarespace's forwarding activates
  over **24 to 48 hours**, a fact its UI only states after you save a rule, and its CDN
  serves the parking page at the root until then.
- **Attempted to bypass forwarding entirely** by pointing the apex at Heroku with an ALIAS
  record, which would have made the root work immediately. Blocked: Squarespace rejects
  ALIAS on a DNSSEC-signed zone, and DNSSEC is enabled for this domain. Turning DNSSEC off
  is a security decision for the owner, so the attempt was reverted rather than forced.
- **The forwarding rule was deleted and recreated** in the course of that attempt, which
  restarted the 24 to 48 hour activation window. Apex A records, the www CNAME, and the
  SPF/DMARC/DKIM records were all verified restored afterwards, and www never stopped
  serving.
- **`wsgi.py` gained a canonical host redirect** (any non-canonical host to `SITE_URL`,
  path and query preserved). It is inert while the apex routes through Squarespace, and
  means only `heroku domains:add` is needed if the apex is ever pointed at Heroku.
- `arbiterai.tech` was removed from the Heroku app again, so certificate management no
  longer reports a permanent validation failure for a domain that does not point there.

## 2026-09-04 — clinical NLP on ingestion, and a product roadmap

- **Research.** Clinical NLP tooling was evaluated by actually installing candidates against
  the worker's exact pins and running them on the de-identified synthetic note. Adopted:
  medspacy 1.3.1 (sections, sentence splitting, ConText assertion), en_core_med7_lg 1.1.0
  (medications with dose, route, frequency), en_ner_bc5cdr_md 0.5.4 (problems), and regex
  rules for labs, vitals, allergies and follow-up. Rejected for now, with reasons in
  `platform/docs/FEATURES_ROADMAP.md` appendix A: scispaCy's linker, MedCAT, GLiNER-biomed,
  OpenMed, Stanza. The 7B model is deterministic and schema-valid but unreliable on
  assertion and invents units, so it is an optional attribute filler, off by default.
- **`db/migrations/`** with `03_apply_migrations.sh` (first init) and `make migrate`
  (existing volumes), recorded in `schema_migrations`. First migration: `clinical_facts`,
  de-identified structured facts with assertion status, optional codes, a chunk/page
  citation and confidence, under the same row-level security policy as `chunks`.
- **Synthetic corpus** now includes two negated findings, a family-history line, an
  allergy with reaction (or NKDA) and an LDL per document, and the manifest carries
  `gold_facts`. `eval/run_extraction_eval.py` (`make eval-extraction`) scores precision,
  recall and F1 per fact kind, with assertion required to match for problems, and reports
  separately how many negated or family-history conditions were wrongly stored as present.
- **`platform/docs/FEATURES_ROADMAP.md`.** What to build on the fact table, mapped against
  Reveleer's public products: evidence packets, MEAT-backed condition validation with the
  public CMS-HCC crosswalk, HEDIS-style measure evidence (NCQA license required for
  software), care gaps, RADV packets, cohort queries, suspecting last and only with
  counsel. Includes the licensing table for the code sets and the human-in-the-loop
  guardrails that keep this a documentation product.
- **`worker/annotate.py` (new), wired into the ingest graph after de-identification.**
  Three layers, cheapest first: regex rules for labs, vitals, allergies, medication lines,
  diagnosis lists, family-history phrases and follow-up; Med7 and bc5cdr named-entity
  models merged by character offset; medspacy ConText for assertion, with leading negation
  cues trimmed from NER spans so "Denies chest pain" is negated rather than stored. The
  sectionizer gained newline-anchored rules for bare headers, and the allergy section no
  longer marks everything after it as hypothetical. Placeholder tokens are single tokens
  and never become facts. PyRuSH's token-level logging is disabled at import so
  de-identified text never reaches container logs. `ANNOTATE=0` bypasses the node.
- **Every fact carries a citation.** `chunks` gained page-relative character offsets
  (`db/migrations/002_chunk_offsets.sql`); each fact links to the chunk with the largest
  span overlap, so the existing `[chunk_id]` citation and validation gate work unchanged.
  254 of 254 facts in the synthetic corpus have a chunk. Re-ingest replaces a document's
  facts along with its chunks and PHI tokens.
- **`GET /v1/patients/{external_id}/facts`** on the gateway (scope `query`, row-level
  security, `active=true` hides absent, family, conditional and possible assertions),
  audited as `facts.read`. This is the evidence-packet primitive from the roadmap.
- **Optional LLM attribute filler** (`ANNOTATE_LLM=0` by default): schema-constrained
  extraction over section bodies, every span checked verbatim against the text and
  through the PHI leak check, used only to fill attributes the other layers missed.
  Live-tested once: 32 seconds per page on this machine and it added nothing on the
  synthetic note, hence off.
- **Worker image** is a two-stage build (a builder compiles the four packages with no
  arm64 wheels; the runtime installs offline from those wheels), plus the bc5cdr config
  patch that spaCy 3.8.16 needs. 2.65 GB to 3.15 GB. Annotation measured at a median of
  36 ms per page inside the container.
- **`worker/deid.py`: bare five-digit numbers need address context** (ZIP pattern score
  0.6 to 0.35), because `WBC 11000` was being scrubbed as a ZIP code.
- **Tests: 122 passed, 2 skipped, 2 xfailed.** 57 new tests run the real models on the
  synthetic text, clean and OCR variants: assertion classes, medication attributes, lab
  values, header variants, placeholder safety, silent logging, offsets, the LLM merge with
  stubbed HTTP; 5 endpoint tests with a fake pool.
- **Extraction eval, 20 documents, 254 facts:** problems F1 1.00 with assertion required,
  medications 0.98 (name, dose and frequency), labs 0.99, vitals 1.00, allergies 1.00.
  Every miss is explained: one Tesseract misread (`fisinopril`), one lab name scrubbed by
  the de-identifier on an OCR page (`HbAic` read as a name). Zero negated or family
  conditions stored as present once the scorer's own artifact is discounted.
- **QA eval on the regenerated corpus:** accuracy 0.95, zero cross-patient leaks, zero
  validation failures, de-id recall 0.992. The one survivor is an MRN whose `MRN:` label
  Tesseract read as `MAN:`, so the label-anchored recognizer did not fire. A pre-existing
  OCR gap surfaced by new random identifiers, now in `TODO.md`.

## 2026-09-04 — test data at scale

- **`platform/docs/DATASETS.md`.** Verified catalog of every usable corpus: MIMIC-IV-Note
  (2.65M de-identified notes) and MIMIC-III (2.08M) via PhysioNet credentialing, with the
  quoted rules on local models and third-party APIs; the n2c2/i2b2 gold sets for
  de-identification recall; the open sets and which licenses forbid commercial evaluation
  (CC BY-NC covers PMC-Patients and Asclepius); scanned-document sets for the OCR router;
  Synthea measured at 50 records per second on this machine with a recipe to 1.23M
  documents; and a pgvector benchmark at one million vectors.
- **`scripts/make_synthetic_docs.py`: scanned pages are 13 KB, not 2 MB.** The scan
  variant embedded a decoded bitmap; it now embeds a hard-thresholded 1-bit image stream
  with no dither. Verified unchanged extraction on two scanned documents.
- **Java 21 installed** (Homebrew, keg-only at `/opt/homebrew/opt/openjdk@21`) to run
  Synthea. No launchd items.

## 2026-09-04 — re-identification fixed, titles are not names, site polish live

- **Query path: document tokens are now re-identified** (`worker/reid.py`). The retrieved
  chunks and the question are renumbered into one token namespace per query, with an index
  of where each token came from. After validation, only the tokens the answer uses are
  restored: question tokens from memory, document tokens decrypted from `phi_tokens` under
  the tenant key. Before, only the question's map was applied, so "who is the attending
  physician?" returned a placeholder and a question about Dr. Patel could name Patel where
  the chart said Young. Verified live: the same question now returns "Dr. Hawkins".
- **De-identification: bare titles and field labels are no longer PERSON spans.** spaCy was
  tagging "Dr" as a person, so charts read `<PERSON_2>. <PERSON_1>` and the model answered
  with the title as the name. PERSON spans are trimmed of leading titles ("Dr", "Mrs") and
  trailing labels ("DOB", "Date"), and dropped if nothing remains.
- **Synthetic scans: grayscale again, still small.** Yesterday's 1-bit 150 dpi scans were 13
  KB but OCR'd worse (drug names came out as "metiormin" and "fisinoprif"; extraction F1 on
  medications fell from 0.98 to 0.90). The measured cause was the encoding, not the fix for
  the 2 MB bloat. Scans are now the original 150 dpi grayscale embedded as a compressed
  stream, 45 KB per page and pixel-identical to the validated corpus; `--scan-mode bilevel`
  gives 1-bit at 300 dpi (30 KB) as an opt-in fax-realism mode. Extraction after the change:
  problems 1.00, medications 1.00 by name and 1.00 by name+dose+frequency, labs 0.99,
  vitals 1.00, allergies 1.00. QA eval unchanged: accuracy 0.95, zero cross-patient leaks,
  de-id recall 0.992 with the same single OCR-label survivor.
- **Site polish deployed (release v9).** Static ledger reads as completed; every text pair
  clears WCAG AA (brass button 3.2 to 6.1, kicker 4.3 to 6.5, badges 4.1 to 5.8 and 6.1);
  scroll padding under the sticky header; visible required-field markers and an 18 px
  consent checkbox; smooth scroll gated on reduced-motion; full Open Graph and Twitter meta;
  footer year baked at build time; docs examples use the platform's real `hipaa_live_`
  prefix and a `<your-deployment>` host; the dead Netlify, Vercel and `_headers` files are
  gone. Copy and claims untouched.
- **`TODO.md` opens with a needs-you table**: a deep link and the exact value to enter for
  each item only the founder can do.
- Tests: 130 passed, 2 skipped, 2 xfailed.

## 2026-09-04 — blog section

- **`site/pages_blog.py` (new), plus a blog index and the first article.** "Medical record
  acronyms: what each one means and why it exists", fourteen terms with their history and
  why each matters to software, published from a supplied PDF.
- **The PDF's text layer had broken ligatures**, so a straight paste would have shipped a
  page of typos: "The" extracted as "Te" thirty times, plus "sofware", "afer", "ofen",
  "lef", and 45 `fi`/`ff` ligature characters. All repaired and verified as zero matches in
  the built output. The article's line that no HIPAA certification exists is preserved
  verbatim; it is the same position the security page takes.
- **The nine diagrams were vector drawings, not images**, so they were rebuilt in the site's
  palette: a fourteen-term timeline, the 1893 cause-of-death list against a modern ICD-10-CM
  code, the Mayo folder before and after 1907, free text against SOAP, the HIPAA rulemaking
  timeline, the Sweeney re-identification funnel, regulator reach before and after HITECH
  (inline SVG), the HITECH adoption bars, and an HL7 v2 message beside the same patient as
  FHIR.
- **Built for crawlers**: both pages in `sitemap.xml` with the article carrying its
  publication date as `lastmod`; `BlogPosting` and `BreadcrumbList` structured data on the
  article and `Blog` on the index, all valid JSON; `og:type=article` with
  `article:published_time` on the post only; an RSS feed at `/feed.xml` linked from every
  page's head; Blog added to the nav and the footer. The PDF is downloadable from the
  article, but the HTML is canonical.
