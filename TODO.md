# TODO before real PHI

## Needs you (one click each)

| what | where | what to do |
|---|---|---|
| Dyno plan | https://dashboard.heroku.com/account/billing | If you still want Eco ($5/mo, sleeps after 30 min idle), subscribe there, then tell me and I run the switch. Staying on Basic ($7/mo, never sleeps) needs nothing. |
| Apex domain `arbiterai.tech` | https://arbiterai.tech | Done: the Squarespace forwarding activated on 2026-09-04 and the apex now 301s to `https://www.arbiterai.tech`. Nothing to do. |
| **PhysioNet credentialing (now the critical path)** | 1. https://physionet.org/settings/credentialing/  2. https://physionet.org/about/citi-course/  3. https://physionet.org/content/mimic-iv-note/2.2/ | Complete the CITI "Data or Specimens Only Research" course (affiliate as MIT to avoid fees; upload the completion *report*), submit the credentialing form, then sign the DUA at the bottom of the MIMIC-IV-Note page. In the research description say: evaluating an open-source (Apache-2.0) clinical de-identification and document-QA pipeline, github.com/yoonbo1/arbiterai; results published as benchmarks. Once credentialed, also request the de-identification gold-standard corpus (see the i2b2 row). |
| De-id recall gold sets: n2c2 (portal down) | https://portal.dbmi.hms.harvard.edu/projects/n2c2-nlp/ → "Need help? Contact us!" | Checked 2026-09-05: the portal says "The n2c2 datasets are temporarily unavailable" with no date, and there is no email address; the only channel is that form. Fill it with: name; your email; "In regards to" = **n2c2 Data**; message: *I am requesting the 2014 De-identification and Heart Disease Risk Factors corpus (and 2016 CEGS N-GRID de-identification track) under the corporate DUA to benchmark an open-source de-identification pipeline (github.com/yoonbo1/arbiterai). The portal shows the datasets as temporarily unavailable. Could you tell me when access requests will reopen, and whether I can submit the DUA now so it is queued?* Then check the page weekly. |
| Governing law in the terms | https://www.arbiterai.tech/terms.html | Ask counsel for the jurisdiction and venue; send me the wording. |
| Make the repo public and license it | https://github.com/yoonbo1/arbiterai | Done 2026-09-05: repo public; `LICENSE` is Apache-2.0 (say if you prefer MIT and I swap it); CI badge and GitHub links on the site added the same day. |
| LinkedIn | send me the URL | The about page and author strip link to email and GitHub only until I have it. |
| Search Console | https://search.google.com/search-console | Add property `www.arbiterai.tech` (DNS or HTML-tag verification; I can add the tag), then submit `https://www.arbiterai.tech/sitemap.xml`. |
| i2b2 2014 de-identification run | blocked on the n2c2 row above | Same corpus, same portal. While it is down, the fallback with real identifiers is the PhysioNet de-identification gold-standard corpus (2,434 nursing notes, PHI annotated), which needs the same PhysioNet credentialing as MIMIC, so the PhysioNet row is now the critical path: https://physionet.org/content/deid/1.1/ ("apply for access to the gold standard corpus" after credentialing). |

Everything below this table is engineering and gets done without you.

## Priorities (ranked 2026-09-05, after the repositioning)

The goal changed on 2026-09-04: Arbiter is proof of expertise for a healthcare AI engineering
role and a seed for a validation-layer business, not a product heading for production PHI.
Ranking follows from that: first what makes the work public and checkable, then what a
technical reviewer would catch, then work that produces new numbers and write-ups, then data
and scale, then dev-box hygiene. Production safeguards are last because the site now says,
correctly, that whoever runs this against real records does so under their own program.

### 1. Make it public and seen (this week; mostly you, one click each; see the table above)
1. ~~Choose the licence and flip the repo public.~~ Done 2026-09-05 (public, Apache-2.0, CI, GitHub links on the site).
2. Request the i2b2/n2c2 2014 de-identification corpus. **Blocked 2026-09-05: the n2c2 portal says the datasets are temporarily unavailable.** Send the contact-form message in the table above, and start PhysioNet credentialing now because it also unlocks the PhysioNet de-identification gold-standard corpus, the fallback with real identifiers.
3. Distribution per the brief: drafts are in `site/DISTRIBUTION.md` (LinkedIn headline and About, four posts under 150 words, five HN submissions with the first comment and the Show HN text). You post.
4. Search Console: add the property, submit the sitemap. Five minutes.
5. Send the LinkedIn URL for the about page and author strip.

### 2. Credibility fixes a code reviewer would catch (me; days)
6. `audit_log` is not under RLS: `app_rw` can read every tenant's rows. The security page admits it; fix it and update the page.
7. ~~`job.query.completed` is written for validation-failed queries too. Record the outcome so the audit trail distinguishes a rejected answer from a delivered one.~~ Done 2026-09-05: a rejected query writes `job.query.rejected` with the reasons in `detail`; only a delivered answer writes `job.query.completed` (`tests/test_graph_query.py`).
8. `jobs.request` stores the raw question and patient id before de-identification. This is the one gap that contradicts invariant 1 in spirit; de-identify or encrypt before persisting.
9. ~~Escalation to the same model at temperature 0 (post-mortem 3 says it is open): skip when the tiers are identical, and make the large tier configurable to a real larger model.~~ Done 2026-09-05: `llm.tiers_identical()` skips the escalation and records `escalation_skipped` when `LARGE_MODEL_URL`/`LARGE_MODEL` resolve to the small tier; point them at a larger model to re-enable it.
10. Plaintext `patients.external_id`, `content_hash = md5(storage_uri)`, and the `storage_uri` left behind by a failed ingest. Three small fixes, each a thing a reader of `init.sql` will notice.
11. `contains_phi` ignores dates and locations in the output check. Decide (Safe Harbor says they are identifiers) and document the decision on the security page either way.
12. Move the custom Presidio recognizers into a delimited module and open the four upstream PRs the brief lists (labelled MRN, NANP with extension, title-anchored names, dosing-frequency date filter). Each PR is a portfolio item and links from its post.

### 3. Work that produces new numbers and new posts (me; weeks)
13. Protect pass before de-identification for eponyms, anatomy and lab names (`Foley`, `Cushing`, `WBC 11000`, `HbAic`). A measured false-positive rate on the production spaCy model is a post in itself.
14. The open 0.992: OCR-corrupted identifier labels (`MAN:` for `MRN:`). Edit-distance tolerance on labels, or treat any 6 to 10 digit run on the demographics line as an identifier.
15. Eval extensions so the numbers mean more: negative questions, multi-document patients, cross-patient probes that name another patient, and the Safe Harbor categories the corpus never exercises (ages over 89, device serials, account numbers).
16. Judge quality: measure agreement on a labelled set; try claim-level checking instead of one number from a 7B model. Follows directly from post-mortem 3.
17. Structured lookup over `clinical_facts` in the query graph, with the same citations.
18. Facility names: decide whether they are geography under your Safe Harbor reading; add the recognizer if so.
19. Tesseract misreads propagating into answers (`fisinopril`, `HbAtc`): drug-name and lab-name dictionary correction, or the VLM route on a GPU box.
20. Concept normalization (ICD-10-CM and RxNorm alias index), fuzzy section headers on OCR, the scorer artifact for family-history duplicates.

### 4. Data and scale (you start the applications; I do the rest)
21. PhysioNet credentialing for MIMIC-IV-Note (weeks of lead time; real notes for the extraction eval).
22. n2c2 2018 track 2 and i2b2 2010 for a real extraction evaluation; an in-house set of about 100 OCR'd pages with span-level gold.
23. Synthea multi-document generator (about 20 document types per patient) at 60,000 patients on an external SSD; then `halfvec` and the per-tenant index partition load test.

### 5. Dev-box hygiene (me; whenever)
24. Ollama as a managed service; cache OCR so `choose_route` does not run Tesseract twice; asyncpg pool validation after a Postgres restart; retry with backoff for transient model errors; split `env_file` secrets per service; widen `api_keys.key_prefix`; `make venv` never installs presidio, spaCy or psycopg (they were pre-installed on this machine; CI installs the gateway, worker and dev requirements instead, so mirror that in the Makefile); verify the `gpu` profile, `vlm` route and Postgres checkpointer on a GPU box.
25. Dyno plan (Eco vs Basic) and governing law in the terms: whenever you feel like it; nothing depends on them.

### 6. Deferred: production-PHI safeguards
Everything under "Gates" and "Safeguards the code does not provide" below (BAAs, MFA and SSO, WORM audit storage, KMS-backed keys, mTLS, multi-AZ, air-gapped model host, risk analysis and policies). Not this project's job now; the security page says so. Keep the list current in `platform/docs/HIPAA_CONTROLS.md` because it is what a deployer reads.



Derived from `platform/docs/HIPAA_CONTROLS.md` plus what the first end-to-end run of the
code exposed. Nothing on this list is optional for production PHI. Not legal advice; review
with a compliance officer.

## Gates (from HIPAA_CONTROLS.md "Non-negotiables")

- [ ] Model host has no outbound internet: pull weights once, then air-gap or allowlist.
- [ ] Every third party touching the machine or data has a BAA (cloud, GPU host, monitoring, support).
- [x] Eval gates pass on synthetic data: de-id recall >= 0.99, zero cross-patient leaks. (1.000 clean / 0.992 OCR corpus, 0 leaks in every run.)
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
- [x] De-identification recall gaps seen on synthetic data: no US street-address recognizer, cities tagged as PERSON. (Address recognizer plus union-merge added 2026-09-03; ZIP survivors 14/20 to 0/20.) Still open: the `00` prefix of `001-555-...` fax numbers, and the whole thing re-measured on n2c2 / i2b2.
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

## Test data (2026-09-04)

- [ ] Start PhysioNet credentialing (CITI course, application, per-dataset DUA) for MIMIC-IV-Note; ask PhysioNet in writing whether internal evaluation of a commercial product counts as "scientific research" under license 1.5.0.
- [ ] Apply to Harvard DBMI for the n2c2 2014 and 2016 de-identification sets; they are the only way to measure recall on realistic identifiers.
- [ ] Extend `make_synthetic_docs.py` to read all Synthea tables and emit ~20 document types per patient with gold PHI offsets and coded facts (list in `docs/DATASETS.md` §3); run at 60,000 patients on an external SSD.
- [ ] Load-test tenant isolation of the vector index: a single global HNSW with a tenant filter loses recall for small tenants; decide between per-tenant partitions and partial indexes before real customers.
- [ ] Consider `halfvec` for `chunks.embedding` (1,170 bytes per vector in the index versus 2,048) before the corpus reaches tens of millions of chunks.

## Found reviewing the query path (2026-09-03)

- [x] **Re-identification only covers the question, never the documents.** `reidentify` restores tokens using the map from scrubbing the question. Tokens the model copies out of retrieved chunks (`<PERSON_3>` for the patient, `<PERSON_2>` for the attending) are never looked up in `phi_tokens`, so an answer to "who is the attending physician?" comes back as a placeholder. The encrypted per-document map in `phi_tokens` exists precisely for this and is never read on the query path.
- [x] **Token namespaces collide.** Every scrub numbers from `<PERSON_1>`, so the question's `<PERSON_1>` and each document's `<PERSON_1>` are different people with the same label. Demonstrated: question "What did Dr. Patel prescribe?" plus a chunk whose `<PERSON_1>` is Dr. Young produced the answer "Patel was started on metformin", a wrong re-identification. Fix both together: give tokens a per-document namespace (or number them per patient across documents), and have `reidentify` decrypt the cited documents' `phi_tokens` under the tenant key and restore only those, plus the question's own.
- [ ] The output leak check (`contains_phi`) deliberately ignores `DATE_TIME` and `LOCATION`, so a raw date or address in an answer would pass. Dates and geography smaller than a state are Safe Harbor identifiers. Decide whether that is acceptable for the product and document it, or tighten the check.

## Found by the eval harness (synthetic data, 20 documents)

- [ ] `audit_log` is not under RLS: `app_rw` can read every tenant's rows. Add a policy or a tenant-scoped view.
- [x] `job.query.completed` is written for validation-failed queries too, so the audit trail cannot distinguish a rejected answer from a delivered one. Record the outcome in `action` or `detail`. (Done 2026-09-05: `job.query.rejected` with `detail.reasons`; `job.query.completed` only for delivered answers.)
- [x] Escalation re-runs the same model at temperature 0 when `LARGE_MODEL` equals `SMALL_MODEL`, which cannot change the verdict and costs 8x. Either configure a genuinely larger model for the large tier or skip escalation when the tiers are identical. (Done 2026-09-05: skipped when the tiers resolve to the same endpoint and model, recorded as `escalation_skipped`, not counted as an escalation.)
- [ ] The grounding judge is a 7B model asked for a single number; it is sensitive to formatting. Consider claim-level checking or a calibrated threshold, and measure judge agreement on a labelled set.
- [ ] Tesseract misreads on scanned pages propagate into answers (`fisinopril` for `lisinopril`, `HbAtc` for `HbA1c`). Route low-confidence pages to the VLM on a GPU box, or add a drug-name dictionary correction step.
- [ ] Ages over 89 and other Safe Harbor identifiers not present in the synthetic corpus (device serials, biometric identifiers, full-face photos, vehicle identifiers, account numbers) are not exercised. Extend the synthetic generator before trusting recall.
- [ ] The eval only ingests one document type and asks two gold questions per patient. Add negative questions (answer not in record), multi-document patients, and cross-patient probes that name another patient.

## Site (it is live now, so these are live defects)

- [x] **The apex `arbiterai.tech` does not serve the site yet.** (Forwarding activated 2026-09-04; the apex 301s to www.) Squarespace forwarding takes 24 to 48 hours to activate and the clock restarted on 2026-09-03 when the rule was recreated. Deeper paths forward already; the root still shows Squarespace's cached parking page. Decide which ending you want: wait it out, move DNS to Cloudflare (supports DNSSEC and apex CNAME flattening, so the apex could serve Heroku directly with no forwarding), or turn off DNSSEC at Squarespace and use an ALIAS record. The third is a security downgrade and is your call, not one to make casually for a company selling security.

- [x] Do not publish SOC 2 or HITRUST claims until the report is issued. (Repositioning 2026-09-04: the attestations block is gone; the about page states no report is claimed.)
- [x] Confirm claims on the Security and Pricing pages that are not yet backed. (Repositioning 2026-09-04: pricing page, SLA, pen-test and BAA claims all removed.)
- [x] **Set `FORM_ENDPOINT` on the Heroku app.** (Moot: the form and the `/submit` handler were removed on 2026-09-04; contact is email and GitHub.)
- [ ] Governing law and venue in the terms. Low priority now: the terms cover only the website, there is no customer agreement, and nothing is sold.
- [x] About page. (Repositioning 2026-09-04: single author page. Still wants the LinkedIn URL and, optionally, a one-line bio.)
- [x] Product page ledger (`ledger(animate=False)`) renders every row at 45% opacity with empty check marks; mark rows `done` when not animating.
- [x] Contrast below WCAG AA: white on brass buttons (3.2:1), kicker `#8F6E2B` on frost (4.3:1), the two badge styles (about 4.1:1).
- [x] Stale host configs now that the site runs on Heroku: `netlify.toml`, `vercel.json` and `_headers` are all dead files there (`wsgi.py` applies the headers instead). Either delete them or keep them working: `vercel.json`'s `cleanUrls: true` would 308-redirect every `.html` link, canonical and sitemap URL.
- [x] Sticky header: add `html{scroll-padding-top:80px}` so anchors like `#baa` clear it by design rather than by section padding.
- [x] Mark required form fields visibly; enlarge the consent checkbox.
- [x] Align the docs page's credential prefix (`arb_live_`) and API host (`api.arbiterai.tech`) with the platform (`hipaa_live_`, no public host yet).
