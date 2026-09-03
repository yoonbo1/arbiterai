# HIPAA-oriented local AI for medical documentation

Queue-based, multi-tenant RAG pipeline: FastAPI gateway → Redis Streams → LangGraph workers →
local models (vLLM on a GPU box, Ollama on Apple Silicon) + pgvector. Runs on one machine for the 100-request test; same containers
scale out on Kubernetes later. See `docs/CLOUD_OPTIONS.md` for the scale-up plan and
`docs/HIPAA_CONTROLS.md` for what this code does and does not cover.

```
gateway/   FastAPI: API keys (hashed), scopes, rate limits, tenant resolution, admin endpoints
worker/    LangGraph graphs (ingest, query), Presidio de-id, OCR→VLM routing, hybrid retrieval, audit
db/        Postgres schema: tenants, api_keys, patients, documents, chunks (pgvector), phi_tokens, audit_log, RLS
scripts/   Synthetic-document generator (with injected fake PHI), tenant bootstrap
eval/      100-request harness: de-id recall, leak rate, accuracy, latency, cost
```

## Quick start (one machine, no GPU required)

Default profile = postgres, redis, embeddings (local arm64 service, `BAAI/bge-small-en-v1.5`),
gateway, worker. The language model is any OpenAI-compatible endpoint named in `.env`.

```bash
cp .env.example .env            # replace every change-me (openssl rand -hex 24); .env is git-ignored

# Apple Silicon / no NVIDIA GPU: Ollama on the host, Metal-accelerated.
brew install ollama
OLLAMA_HOST=0.0.0.0:11434 nohup ollama serve > /tmp/ollama.log 2>&1 &   # nohup: outlives the shell. 0.0.0.0 so containers reach it
                                             # via host.docker.internal (dev only: LAN-exposed)
ollama pull qwen2.5:7b-instruct              # SMALL_MODEL/LARGE_MODEL in .env; VLM_URL stays empty (scans fall back to OCR)

docker compose up -d --build                 # first build downloads en_core_web_lg (~560 MB)
python -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python scripts/make_synthetic_docs.py --n 100    # writes data/synthetic/ (mounted at /data in the worker)
./scripts/bootstrap_tenant.sh "Test Clinic"  # prints tenant_id + a one-time API key

API_KEY=hipaa_live_... TENANT_ID=<uuid> \
DATABASE_URL=postgresql://app_rw:<PG_APP_PASSWORD>@127.0.0.1:<PG_HOST_PORT>/hipaa \
  .venv/bin/python eval/run_eval.py --manifest data/synthetic/manifest.json --limit 1
```

`make up / down / synth / eval / test` wrap the same commands.

NVIDIA box: `docker compose --profile gpu up -d --build` adds `vllm-small`
(`SMALL_MODEL_URL=http://vllm-small:8000/v1`); add `--profile vlm` and `VLM_URL=http://vllm-vlm:8000/v1`
for the vision model on a second GPU. The `vllm/vllm-openai` image is CUDA + linux/amd64 only.

Notes for a dev machine:
- The app connects to Postgres as `app_rw`, the role RLS applies to; `hipaa` (owner) is for init only.
- `CHECKPOINTER=none` by default. `postgres` would persist pre-de-identification text; see `.env.example`.
- `docker compose down -v` wipes the database (needed after any change to `db/`).

## API

| Method | Path | Scope | Notes |
|---|---|---|---|
| POST | /v1/documents | ingest | `{patient_external_id, doc_type, storage_uri}` → 202 `{job_id}` |
| POST | /v1/queries | query | `{patient_external_id, question, max_chunks}` → 202 `{job_id}` |
| GET | /v1/jobs/{id} | any | status + result; other tenants' jobs return 404 via RLS |
| POST | /admin/tenants | admin token | create tenant (`baa_signed` gates PHI processing) |
| POST | /admin/tenants/{id}/keys | admin token | mint key; plaintext shown once |
| DELETE | /admin/keys/{id} | admin token | revoke; takes effect within 60 s |

Send `Idempotency-Key` on POSTs so client retries never double-process or double-bill.

## How isolation works

1. The API key resolves to a `tenant_id`; clients never send one.
2. Every worker transaction runs `SET LOCAL app.tenant_id`, and Postgres row-level security
   filters every PHI table. A bug in app code cannot read another tenant's rows.
3. Retrieval additionally hard-filters on `patient_id`, so one patient's chart never surfaces
   for another patient's question.
4. Vector store holds de-identified text only; the reversible PHI map lives in `phi_tokens`,
   encrypted with a per-tenant key.

## Cost levers already wired in

- Page routing: native text (free) → Tesseract (cheap) → VLM (expensive) only on low-confidence pages.
- Small model first; large model only if validation fails, and at most one escalation.
- Hybrid retrieval + tight `k` keeps prompts short.
- Per-job token and cost accounting in `jobs`, so per-tenant invoices and hot spots come from one table.

## Graduating from synthetic to real data

Pass the eval gates first (see `eval/`): de-id recall ≥ 0.99 on injected PHI, zero cross-patient
leaks, cost/request where you need it. Then complete a written risk analysis, sign BAAs, enable
disk encryption + TLS + no-egress on the model host, and only then load real (or MIMIC) data.
