# Arbiter AI

[![CI](https://github.com/yoonbo1/arbiterai/actions/workflows/ci.yml/badge.svg)](https://github.com/yoonbo1/arbiterai/actions/workflows/ci.yml) [![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Arbiter AI is an open reference implementation of HIPAA-safe document AI: de-identification
before any model call, cited and verified answers, database-enforced patient isolation, and
an append-only audit trail — with the evaluation harness that proves each of those
properties holds.

Built and maintained by one engineer, Yoonbo Cho, to have a public, checkable answer to
"what does a correct clinical document pipeline look like?". It is not a product and not a
hosted service. It has never processed real PHI; every record it ships is synthetic. No
Business Associate Agreement is offered. If you want to run it against real records, run it
in your own environment under your own compliance program.

Site: https://www.arbiterai.tech (architecture, security model, docs, evals, post-mortems).

## Architecture

```
document ─► text extraction (native / OCR / vision routing)         worker/extract.py
         ─► Presidio de-identification, reversible per-tenant map    worker/deid.py
         ─► clinical facts (sections, assertion, meds, labs)         worker/annotate.py
         ─► chunk + embed (pgvector, 384-dim)                        worker/store.py
question ─► de-identify ─► retrieval scoped to (tenant, patient)     worker/retrieval.py
         ─► answer with [chunk] citations (local 7B)                 worker/llm.py
         ─► validate: citation required, faithfulness ≥ 0.7,
            PHI-leak check; one escalation at most                   worker/graph.py
         ─► re-identify, only for the caller, only the tokens used   worker/reid.py
         ─► audit write (append-only)                                 db/init.sql
```

## Invariants, and where each is enforced and tested

| invariant | enforced | tested |
|---|---|---|
| Nothing reaches a model until the state is de-identified | `deidentified` assertions in `worker/graph.py` (annotate, chunk_embed, generate); Presidio in `worker/deid.py` | `tests/test_deid.py`; de-id recall in `eval/run_eval.py` |
| The PHI map never enters the vector store | map encrypted with `pgp_sym_encrypt` into `phi_tokens`; chunks hold placeholders only (`worker/store.py`) | `deid_recall_strict` scans every stored chunk for every injected identifier |
| Retrieval is hard-filtered on patient | `WHERE tenant_id=… AND patient_id=…` in `worker/retrieval.py`, on top of row-level security | `test_query_is_hard_filtered_by_tenant_and_patient`; `cross_patient_leaks` = 0 in every eval run |
| Tenant identity comes from the credential, never a client field | HMAC-SHA256 key lookup in `gateway/auth.py`; `app.tenant_id` set transaction-locally; app connects as `app_rw`, a role RLS applies to | `tests/test_auth.py`; cross-tenant probes (key B → 404 on tenant A's job) |
| The audit log is append-only and tenant-scoped | `REVOKE UPDATE, DELETE ON audit_log FROM app_rw` and the `tenant_isolation` RLS policy on `audit_log` in `db/init.sql` (`db/migrations/003_audit_log_rls.sql` for existing databases) | verified as `app_rw` with `app.tenant_id` = A: UPDATE/DELETE → permission denied; 0 of tenant B's rows visible, all of A's; INSERT for B → policy violation (`tests/test_schema.py` pins the policy) |

The superuser finding, in plain words: the services originally connected as the Postgres
owner, which bypasses row-level security, so the isolation the code described did not exist.
Fixed, with probes. Details on the security model page and in the post-mortems.

## Quickstart

Prerequisites: Docker (validated with Colima on Apple Silicon), Python 3.12, and a local
model: Ollama with `qwen2.5:7b-instruct` on Apple Silicon, or the vLLM `gpu` compose profile
on NVIDIA. No cloud APIs are called, ever.

```bash
cp platform/.env.example platform/.env   # set every change-me
make up                                  # postgres, redis, embeddings, gateway, worker
make synth N=20                          # synthetic records with injected fake identifiers
make bootstrap                           # dev tenant + API key -> platform/.env.dev-tenant
make eval LIMIT=20                       # ingest, de-id recall, 40 gold questions, leaks, latency, cost
make eval-extraction LIMIT=20            # clinical-fact extraction against gold
make test                                # 227 tests with the clinical extras; CI runs 172 without them
```

## Evaluation results

| metric | dataset | value | notes |
|---|---|---|---|
| De-identification recall, whole string | synthetic, 20 records | 0.967 → 1.000 | four iterations in a day |
| De-identification recall, strict per component | synthetic, 20 records | ≈0.81 → 1.000 | the metric that exposed surviving ZIP codes |
| ZIP codes surviving | synthetic, 20 records | 14/20 → 0/20 | |
| Answer accuracy, strict | synthetic, 40 gold questions | 0.575 → 0.975 | |
| Cross-patient leaks | synthetic, every run | 0 | |
| Clinical extraction F1: problems (assertion required) / medications (name, dose, frequency) / labs | synthetic, 20 records | 1.00 / 1.00 / 0.99 | |
| De-identification recall | i2b2 2014 test set | not yet run | the number that matters; needs credentialed access |

On the regenerated corpus that includes OCR'd scans, whole-string recall was 0.992 until
2026-09-05 (one record number survived because Tesseract read its `MRN:` label as `MAN:`).
The MRN recognizer now tolerates one OCR error in the label; the same corpus scores 1.000
whole-string and strict, accuracy 0.975, 0 leaks, 0 validation failures.

## Failure modes I found

Written up as post-mortems on the site's blog: spaCy redacting the word "daily" and breaking
11 of 12 medication lists; an aggregate recall of 0.967 hiding ZIP codes in 14 of 20
documents; a 7B judge scoring identical facts 0.0 or 1.0 by citation placement; and the
services connecting as the Postgres superuser, which silently bypasses RLS.

## What this is not

Not a product, not a hosted service, no BAA, no SOC 2 or HITRUST claim, no real PHI, ever.
`TODO.md` lists everything that would have to be true before real records could be
processed anywhere. Licensed under Apache-2.0; the licence grants no warranty and no
compliance claim.

## Layout

### platform/

| Path | Purpose |
|---|---|
| `gateway/` | FastAPI API gateway. Hashed API keys (HMAC-SHA256 with a pepper), scopes, per-key rate limits, tenant resolution from the key, admin endpoints for tenants and keys. Enqueues jobs, never runs inference. |
| `worker/` | Redis Streams consumer running two LangGraph graphs. Ingest: load -> route pages -> extract (text / OCR / VLM) -> Presidio de-identify -> chunk + embed -> audit. Query: de-identify question -> hybrid retrieval (pgvector + BM25, RRF) -> generate (small model) -> validate (PHI leak, citations, grounding) -> optional one-time escalation -> re-identify -> audit. |
| `db/init.sql` | Postgres schema: tenants, api_keys, patients, documents, chunks (vector(384)), phi_tokens (pgp_sym_encrypt), jobs, audit_log. Row-level security on every PHI table keyed on `app.tenant_id`. |
| `scripts/` | `make_synthetic_docs.py` (synthetic discharge summaries with known fake PHI, clean and "scanned"), `bootstrap_tenant.sh` (creates a tenant and mints a key against the local gateway). |
| `eval/run_eval.py`, `eval/run_extraction_eval.py` | The harness: ingests the corpus, checks de-id recall (whole string and strict per component) on injected identifiers, asks the gold questions, reports accuracy, validation failures, escalations, cross-patient leaks, p50/p95 latency, tokens and cost; the extraction eval scores clinical facts against gold. |
| `docs/` | `DATA_AND_PIPELINE.md` (walkthrough and glossary), `FEATURES_ROADMAP.md`, `DATASETS.md` (public corpora and their licences), `HIPAA_CONTROLS.md` (what the code covers vs what you must add), `CLOUD_OPTIONS.md`. |
| `docker-compose.yml` | postgres (pgvector), redis, embeddings (text-embeddings-inference, bge-small), gateway, worker. GPU-only services (vLLM small model and VLM) are behind a compose profile. |

### site/

| Path | Purpose |
|---|---|
| `build.py` | Wraps each page body in the shared shell (header, nav, footer, meta, JSON-LD) and writes `public/`, `sitemap.xml`, `robots.txt`, `feed.xml`. |
| `pages.py`, `pages_home.py`, `pages_product.py`, `pages_blog.py` | Page bodies as HTML strings: home, how it works, security model, docs, about, contact, privacy, terms, 404, and the blog (post-mortems and the acronyms guide). |
| `assets/` | `styles.css` (ink / frost / brass palette), `main.js` (nav toggle, trace animation), `logo.svg`, `favicon.svg`, `og-image.png`, `medical-record-acronyms.pdf`. |
| `wsgi.py`, `Procfile`, `bin/post_compile` | Heroku deployment: gunicorn + WhiteNoise, security headers (CSP, HSTS, frame-ancestors none), canonical-host and legacy-path redirects, and the build hook that generates `public/`. |

`site/public/` is generated and is not committed. Run `make site` (or `python3 site/build.py` from `site/`).

## Author

Yoonbo Cho · hello@arbiterai.tech · github.com/yoonbo1 · https://github.com/yoonbo1/arbiterai
