# Arbiter AI monorepo task runner.
#   make site   build the marketing site into site/public/
#   make serve-site  serve it locally with gunicorn (same stack as Heroku)
#   make up     start postgres, redis, embeddings, gateway, worker (no GPU services)
#   make down   stop the stack (keeps volumes; `make down-v` wipes them)
#   make migrate apply platform/db/migrations/*.sql to the running database
#   make synth  generate synthetic documents with injected fake PHI (N=20 by default)
#   make eval   run the 100-request eval harness against the local stack
#   make eval-extraction  score extracted clinical facts against the synthetic gold
#   make test   run pytest for gateway/auth.py, worker/deid.py, worker/retrieval.py, worker/annotate.py
#   make venv-clinical  add medspacy + the Med7/bc5cdr NER models to .venv (tests/test_annotate.py)
#
# Host-side Python comes from ./.venv (Python 3.12). Create it with `make venv`.

SHELL := /bin/bash
.DEFAULT_GOAL := help

ROOT      := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PLATFORM  := $(ROOT)/platform
SITE      := $(ROOT)/site
VENV      := $(ROOT)/.venv
PY        := $(VENV)/bin/python
PYTHON312 ?= python3.12
N         ?= 20
COMPOSE   := docker compose --project-directory $(PLATFORM)

.PHONY: help site serve-site deploy-site venv venv-clinical up down down-v ps logs migrate synth bootstrap eval eval-extraction test llm clean

help:
	@grep -E '^#   make' $(MAKEFILE_LIST) | sed 's/^#   //'

# ---------------------------------------------------------------- site
site:
	cd $(SITE) && python3 build.py

# Serve the built site with the same stack Heroku runs (gunicorn + WhiteNoise), so the
# security headers and the 404 fallback behave locally exactly as they do in production.
serve-site: site venv
	cd $(SITE) && $(VENV)/bin/gunicorn wsgi:app --bind 127.0.0.1:8765 --workers 2 --threads 4

# Deploy site/ to Heroku. The app must already exist and have a git remote (see README).
deploy-site: site
	git subtree push --prefix site heroku main

# ---------------------------------------------------------------- python env
venv: $(VENV)/bin/python
$(VENV)/bin/python:
	$(PYTHON312) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r $(PLATFORM)/scripts/requirements.txt -r $(PLATFORM)/requirements-dev.txt
	$(VENV)/bin/python -m spacy download en_core_web_sm

# Clinical NLP layer for tests/test_annotate.py: medspacy (compiles PyRuSH & co. locally), the two
# NER model wheels (--no-deps: bc5cdr's metadata pins spacy<3.8), and the config patch bc5cdr needs
# on spaCy 3.8. Mirrors worker/Dockerfile. ~450 MB download.
MED7_WHL   := https://huggingface.co/kormilitzin/en_core_med7_lg/resolve/main/en_core_med7_lg-1.1.0-py3-none-any.whl
BC5CDR_SRC := https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz
venv-clinical: venv
	$(VENV)/bin/pip install -r $(PLATFORM)/worker/requirements-clinical.txt
	$(VENV)/bin/pip install --no-deps $(MED7_WHL) $(BC5CDR_SRC)
	cfg="$$($(PY) -c 'import en_ner_bc5cdr_md,os;print(os.path.dirname(en_ner_bc5cdr_md.__file__))')/en_ner_bc5cdr_md-0.5.4/config.cfg"; \
	  sed -i.bak -e 's/^include_static_vectors = "True"/include_static_vectors = true/' \
	             -e 's/^include_static_vectors = "False"/include_static_vectors = false/' "$$cfg" && rm -f "$$cfg.bak"
	$(PY) -c "import spacy; spacy.load('en_ner_bc5cdr_md', exclude=['tagger','attribute_ruler','lemmatizer','parser']); spacy.load('en_core_med7_lg'); print('clinical models ok')"

# ---------------------------------------------------------------- stack
$(PLATFORM)/.env:
	@echo "platform/.env is missing. Copy platform/.env.example to platform/.env and set every change-me value." && exit 1

up: $(PLATFORM)/.env
	$(COMPOSE) up -d --build
	$(COMPOSE) ps

down:
	$(COMPOSE) down

down-v:
	$(COMPOSE) down -v

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100 gateway worker

# Apply platform/db/migrations/*.sql to the running Postgres. Idempotent: the same script runs at
# first init (db/03_apply_migrations.sh), and records applied files in schema_migrations.
migrate:
	$(COMPOSE) exec -T postgres bash /docker-entrypoint-initdb.d/03_apply_migrations.sh

# ---------------------------------------------------------------- data + eval
synth: venv
	cd $(PLATFORM) && $(PY) scripts/make_synthetic_docs.py --n $(N)

bootstrap:
	cd $(PLATFORM) && ./scripts/bootstrap_tenant.sh "$(TENANT)"

# Reads TENANT_ID, API_KEY, DATABASE_URL (app_rw on the host port) and GATEWAY from
# platform/.env.dev-tenant, written by `make bootstrap`. LIMIT caps the number of documents.
LIMIT ?= 20
eval: venv
	cd $(PLATFORM) && set -a && . ./.env.dev-tenant && set +a && \
	  $(PY) eval/run_eval.py --manifest data/synthetic/manifest.json --limit $(LIMIT) $(EVAL_ARGS)

# Score clinical_facts against the manifest's gold_facts (run after ingesting with annotation on).
eval-extraction: venv
	cd $(PLATFORM) && set -a && . ./.env.dev-tenant && set +a && \
	  $(PY) eval/run_extraction_eval.py --manifest data/synthetic/manifest.json --limit $(LIMIT) $(EVAL_ARGS)

# ---------------------------------------------------------------- tests
test: venv
	cd $(PLATFORM) && $(PY) -m pytest -q tests

clean:
	rm -rf $(SITE)/public
	find $(ROOT) -name __pycache__ -type d -prune -exec rm -rf {} +

llm: ## Pull the local model and check the Ollama server the worker talks to
	@curl -sf http://localhost:11434/api/tags >/dev/null || { echo "Ollama is not running: start it with 'ollama serve' (or open the Ollama app)"; exit 1; }
	ollama pull qwen2.5:7b-instruct
	@echo "ok: qwen2.5:7b-instruct available at http://localhost:11434 (the containers reach it as host.docker.internal:11434)"
