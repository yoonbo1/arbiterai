# TODO before real PHI

Derived from `platform/docs/HIPAA_CONTROLS.md` plus what the first end-to-end run of the
code exposed. Nothing on this list is optional for production PHI. Not legal advice; review
with a compliance officer.

## Gates (from HIPAA_CONTROLS.md "Non-negotiables")

- [ ] Model host has no outbound internet: pull weights once, then air-gap or allowlist.
- [ ] Every third party touching the machine or data has a BAA (cloud, GPU host, monitoring, support).
- [ ] Eval gates pass on synthetic data: de-id recall >= 0.99, zero cross-patient leaks.
- [ ] Admin endpoints (`/admin/*`) sit behind VPN + MFA, never on the public internet.
- [ ] Rotate `API_KEY_PEPPER`, DB passwords, and `TENANT_KEK` out of `.env` into a secrets manager.

## Safeguards the code does not provide (HIPAA_CONTROLS.md "You add" column)

- [ ] **Unique user identification**: MFA + SSO for an admin console; a named human behind every API key.
- [ ] **Access control**: role review process; issue the `cohort` scope only to population-health roles.
- [ ] **Audit controls**: ship `audit_log` to WORM storage; 6-year retention; scheduled log review.
- [ ] **Integrity**: backups with tested restore; checksum verification of stored documents.
- [ ] **Transmission security**: TLS everywhere including between services (mTLS in-cluster); VPN or private link for tenants. Today ports are only bound to localhost.
- [ ] **Encryption at rest**: full-disk / volume encryption; per-tenant DEKs from KMS or Vault (today `_tenant_key()` derives from an env var); encrypted object storage for source documents.
- [ ] **De-identification**: measure recall on n2c2 / i2b2; tune thresholds; human review sample.
- [ ] **BAAs**: signed with every tenant and every vendor.
- [ ] **Risk analysis and policies**: written risk analysis for this system, incident response plan, workforce training, sanctions policy.
- [ ] **Contingency**: multi-AZ, DR runbook, tested failover.
- [ ] **Telemetry**: self-host Langfuse/LangSmith or send only de-identified spans. Cloud tracing stays off.

## Code-level gaps found during bring-up

- [ ] `jobs.request` stores the raw request (question text, patient external id) before de-identification, contrary to the schema comment. De-identify or encrypt before persisting.
- [ ] The LangGraph Postgres checkpointer (`CHECKPOINTER=postgres`) would persist pre-de-identification text and the plaintext PHI map outside RLS. It is off by default; do not enable it with real data until checkpoint state is encrypted and tenant-scoped.
- [ ] `storage_uri` is client-supplied and opened by the worker. It is now restricted to `DATA_ROOT`; production needs per-tenant object storage prefixes and signed access.
- [ ] Patient `external_id` (typically an MRN) is stored in plaintext in `patients`; the schema comment says "stored encrypted at rest". Encrypt or hash it.
- [ ] The synthetic-data eval only exercises one document type (discharge summary). Add scans of real formats (faxes, forms, handwriting) once de-identified samples exist.
- [ ] The small model runs on the developer's machine via Ollama bound to `0.0.0.0` for container access. Production model hosts need a private network and no LAN exposure.
- [ ] Ollama is a bare background process, not a service, so nothing restarts it and it dies on reboot. It also crashed once with a bus error while idle after roughly 4,500 requests. If that recurs, capture the log and pin a different runner; for anything beyond local dev, run the model host as a managed service.
- [ ] De-identification recall gaps seen on synthetic data: Presidio has no US street-address recognizer (street number and street name fragments survive), city names are sometimes tagged as PERSON, the `00` prefix of `001-555-...` fax numbers survives. Add an address recognizer and tune thresholds with `en_core_web_lg` on n2c2 / i2b2 before the 0.99 gate can be trusted.
- [ ] `documents.content_hash` is `md5(storage_uri)`, not a hash of the bytes. Hash the content so dedupe and integrity checks mean something.
- [ ] A failed ingest leaves a `documents` row containing the client-supplied `storage_uri` (seen with the path-traversal probe). Scrub or drop it.
- [ ] `env_file: .env` hands every secret to both containers (the worker receives `ADMIN_TOKEN`). Split secrets per service.
- [ ] Application errors are not retried; only crash-mid-job redelivery is. Classify transient errors (model or embeddings unreachable) for retry with backoff.
- [ ] The gateway's asyncpg pool does not validate connections after a Postgres restart (masked today because compose restarts the gateway). Add a connection check or `max_inactive_connection_lifetime`.
- [ ] `choose_route` runs Tesseract twice per scanned page; cache the OCR output.
- [ ] `api_keys.key_prefix` is the first 12 characters, which is `hipaa_live_` plus one random character. Widen it if audit-log matching by prefix matters.
- [ ] The `vlm` route, `CHECKPOINTER=postgres`, and the `gpu` compose profile are untested on this machine (no NVIDIA GPU). Verify on a GPU box.

## Found while adding clinical NLP (2026-09-04)

- [ ] **Protect clinical eponyms and anatomy before de-identification.** With the production spaCy model, `Foley catheter`, `Cushing syndrome`, `Right Upper Lobe` and `WBC 11000` were scrubbed as a person, a person, a location and a ZIP code. Build protected character ranges from a lexicon (RxNorm prescribable names followed by a dose, eponym plus `catheter|syndrome|disease|lymphoma|palsy`, anatomy phrases, lab names followed by large integers) and drop Presidio results inside them. Do not use model NER for this; its false positives would become allow-list holes.
- [ ] **Facility names are not scrubbed** ("Johns Hopkins Hospital", "Mercy General ED"). Decide whether facilities count as geography under your Safe Harbor reading and add an ORG/facility recognizer if so.
- [ ] **Section and negation rules are colon-anchored and brittle on OCR.** Bare headers need custom rules (added for the common ones); OCR-damaged cues (`Denles`, `Noevidence`) and shorthand (`FHx`, `(-)`, `?`) are missed. Add fuzzy header matching and the shorthand cue rules, and measure on scanned pages.
- [ ] **Concept normalization is not wired.** `clinical_facts.code` is null. Build an alias index from the public CDC ICD-10-CM files and the NLM RxNorm prescribable subset (both redistributable); LOINC after accepting its license; SNOMED only when a customer brings an affiliate license.
- [ ] **Structured lookup in the query graph.** Facts are written but the query path still retrieves only text chunks. Add an intent-routed lookup over `clinical_facts` that unions the facts' chunk ids into the retrieval pool and prepends `FACT:` excerpts, so "list the medications" is answered from structured rows with the same citations.
- [ ] **The LLM extraction layer is off by default** (`ANNOTATE_LLM=0`) because it costs 25 to 60 seconds per document on this machine. Turn it on when the model runs on a GPU, and only as an attribute filler validated against the text.
- [ ] **OCR-corrupted identifier labels leave identifiers bare.** Tesseract read `MRN:` as `MAN:` on one scanned page and the 7-digit MRN survived de-identification (recall 0.992 on the regenerated corpus). Add edit-distance tolerance for identifier labels, or treat any 6 to 10 digit run on the demographics line as an identifier.
- [ ] **The de-identifier scrubs OCR-mangled lab names** (`HbAic` became a person placeholder, `Pian` for `Plan` became a placeholder), which then hides the lab from extraction. Part of the protect-pass item above; include OCR variants of lab names and section headers.
- [ ] Scorer artifact: `negated_or_family_stored_as_present` counts a legitimately present diagnosis when the synthetic generator lists the same condition under family history. Exclude names also in `problems_present`.
- [ ] **A real extraction evaluation** needs n2c2 2018 track 2 and i2b2 2010 under their data use agreements, plus an in-house set of about 100 OCR'd pages with span-level gold. The synthetic numbers are a floor on a corpus that was written to be easy.

## Found reviewing the query path (2026-09-03)

- [ ] **Re-identification only covers the question, never the documents.** `reidentify` restores tokens using the map from scrubbing the question. Tokens the model copies out of retrieved chunks (`<PERSON_3>` for the patient, `<PERSON_2>` for the attending) are never looked up in `phi_tokens`, so an answer to "who is the attending physician?" comes back as a placeholder. The encrypted per-document map in `phi_tokens` exists precisely for this and is never read on the query path.
- [ ] **Token namespaces collide.** Every scrub numbers from `<PERSON_1>`, so the question's `<PERSON_1>` and each document's `<PERSON_1>` are different people with the same label. Demonstrated: question "What did Dr. Patel prescribe?" plus a chunk whose `<PERSON_1>` is Dr. Young produced the answer "Patel was started on metformin", a wrong re-identification. Fix both together: give tokens a per-document namespace (or number them per patient across documents), and have `reidentify` decrypt the cited documents' `phi_tokens` under the tenant key and restore only those, plus the question's own.
- [ ] The output leak check (`contains_phi`) deliberately ignores `DATE_TIME` and `LOCATION`, so a raw date or address in an answer would pass. Dates and geography smaller than a state are Safe Harbor identifiers. Decide whether that is acceptable for the product and document it, or tighten the check.

## Found by the eval harness (synthetic data, 20 documents)

- [ ] `audit_log` is not under RLS: `app_rw` can read every tenant's rows. Add a policy or a tenant-scoped view.
- [ ] `job.query.completed` is written for validation-failed queries too, so the audit trail cannot distinguish a rejected answer from a delivered one. Record the outcome in `action` or `detail`.
- [ ] Escalation re-runs the same model at temperature 0 when `LARGE_MODEL` equals `SMALL_MODEL`, which cannot change the verdict and costs 8x. Either configure a genuinely larger model for the large tier or skip escalation when the tiers are identical.
- [ ] The grounding judge is a 7B model asked for a single number; it is sensitive to formatting. Consider claim-level checking or a calibrated threshold, and measure judge agreement on a labelled set.
- [ ] Tesseract misreads on scanned pages propagate into answers (`fisinopril` for `lisinopril`, `HbAtc` for `HbA1c`). Route low-confidence pages to the VLM on a GPU box, or add a drug-name dictionary correction step.
- [ ] Ages over 89 and other Safe Harbor identifiers not present in the synthetic corpus (device serials, biometric identifiers, full-face photos, vehicle identifiers, account numbers) are not exercised. Extend the synthetic generator before trusting recall.
- [ ] The eval only ingests one document type and asks two gold questions per patient. Add negative questions (answer not in record), multi-document patients, and cross-patient probes that name another patient.

## Site (it is live now, so these are live defects)

- [ ] **The apex `arbiterai.tech` does not serve the site yet.** Squarespace forwarding takes 24 to 48 hours to activate and the clock restarted on 2026-09-03 when the rule was recreated. Deeper paths forward already; the root still shows Squarespace's cached parking page. Decide which ending you want: wait it out, move DNS to Cloudflare (supports DNSSEC and apex CNAME flattening, so the apex could serve Heroku directly with no forwarding), or turn off DNSSEC at Squarespace and use an ALIAS record. The third is a security downgrade and is your call, not one to make casually for a company selling security.

- [ ] Do not publish SOC 2 or HITRUST claims until the report is issued (currently listed as "In progress" / "Planned", which is accurate).
- [ ] Confirm claims on the Security and Pricing pages that are not yet backed: "Independent penetration test summary: Available", "flow-down BAAs with all subprocessors", "99.9% uptime SLA".
- [ ] **Set `FORM_ENDPOINT` on the Heroku app.** The form now works end to end, but with no endpoint configured the submission is only written to the application log, which is not durable and is a poor place for personal data. Pick a backend (Formspree, Basin, or a Slack/Zapier webhook) and run `heroku config:set FORM_ENDPOINT=... -a arbiterai-site`. No code or CSP change is needed: `wsgi.py` forwards server side.
- [ ] Counsel must set the governing law and venue in the terms. The placeholder is gone; the clause now defers to the customer's signed agreement, which is honest but leaves website-only disputes unaddressed.
- [ ] Add real founder and team bios to the About page. The placeholder callout is removed, so that column is now short. Healthcare buyers check who they are buying from.
- [ ] Product page ledger (`ledger(animate=False)`) renders every row at 45% opacity with empty check marks; mark rows `done` when not animating.
- [ ] Contrast below WCAG AA: white on brass buttons (3.2:1), kicker `#8F6E2B` on frost (4.3:1), the two badge styles (about 4.1:1).
- [ ] Stale host configs now that the site runs on Heroku: `netlify.toml`, `vercel.json` and `_headers` are all dead files there (`wsgi.py` applies the headers instead). Either delete them or keep them working: `vercel.json`'s `cleanUrls: true` would 308-redirect every `.html` link, canonical and sitemap URL.
- [ ] Sticky header: add `html{scroll-padding-top:80px}` so anchors like `#baa` clear it by design rather than by section padding.
- [ ] Mark required form fields visibly; enlarge the consent checkbox.
- [ ] Align the docs page's credential prefix (`arb_live_`) and API host (`api.arbiterai.tech`) with the platform (`hipaa_live_`, no public host yet).
