# HIPAA controls: what the code covers vs what you must add

Not legal advice. Review with a compliance officer before processing real PHI.

| Safeguard (45 CFR 164.3xx) | In this repo | You add |
|---|---|---|
| Unique user identification | Per-tenant API keys with IDs, scopes, prefixes in logs | MFA + SSO for admin console; named human users behind each key |
| Access control / minimum necessary | Scopes, RLS, patient-level retrieval filter, de-identified vector store | Role review process; separate `cohort` scope only for population roles |
| Audit controls | Append-only `audit_log`, per-job accounting, `REVOKE UPDATE/DELETE` | Ship logs to WORM storage; 6-year retention; regular log review |
| Integrity | Content hashes on documents, idempotent jobs | Backups with tested restore; checksum verification |
| Transmission security | Ports bound to localhost | TLS everywhere (mTLS inside cluster), VPN/private link for tenants |
| Encryption at rest | `pgp_sym_encrypt` for PHI token map (per-tenant key) | Full-disk/volume encryption; KMS/Vault for tenant DEKs; encrypted object storage |
| De-identification | Presidio + custom recognizers (`worker/recognizers/`: MRN, phone, clinician name, address; date and title filters), leak check on outputs (see below) | Measure recall on n2c2/i2b2; tune thresholds; human review sample |
| Business associate agreements | `baa_signed_at` gates a tenant | Signed BAAs with every tenant *and* every vendor (cloud, GPU host, monitoring) |
| Risk analysis & policies | — | Written risk analysis covering this system, incident response plan, workforce training, sanctions policy |
| Contingency | Redis AOF, Postgres volume, resumable LangGraph checkpoints | Multi-AZ, DR runbook, tested failover |
| Telemetry | vLLM usage stats disabled; LangSmith cloud tracing off | Self-host Langfuse/LangSmith or send only de-identified spans |

## Non-negotiables before real PHI
1. Model host has no outbound internet (pull weights once, then air-gap or allowlist).
2. Every third party touching the machine or data has a BAA.
3. Eval gates pass on synthetic data: de-id recall ≥ 0.99, zero cross-patient leaks.
4. Admin endpoints are behind VPN + MFA, not the public internet.
5. Rotate `API_KEY_PEPPER` and DB passwords out of `.env` into a secrets manager.

## Output leak check

`worker/deid.contains_phi` runs on every model answer before it is returned (`graph.validate`)
and on the extraction layer's JSON before it is stored (`worker/annotate.py`). Validation runs
before re-identification, so the text it sees still carries `<TYPE_n>` placeholders; a raw
identifier there cannot be a legitimate restore, it can only have come from a chunk the
de-identifier missed. The check therefore applies the scrub's own criteria rather than a looser
set:

- Dates: a DATE_TIME hit counts as a leak when it is calendar-like (month name, numeric or ISO
  date, year, ordinal), the same `recognizers/date_filter` test the scrub applies. Dosing
  frequencies and durations (`daily`, `for 2 weeks`, `48 hours`) are clinical content and pass.
- Geography: a LOCATION hit counts when the address recognizer produced it (labelled address
  line, street line, `City, ST ZIP`, or a ZIP lifted by address context), which is the
  Safe Harbor "geographic subdivision smaller than a state". A bare state or country name from
  NER (`Texas`) passes.
- Names: a PERSON hit goes through the same title and label trim as the scrub, so the bare
  `Dr` that the title-anchored recognizer finds in `Attending: Dr. <PERSON_2>` is not a leak;
  `Attending: Dr. Young` is. (Before 2026-09-05 that answer shape was rejected.)
- Everything else (PHONE_NUMBER, EMAIL_ADDRESS, US_SSN, MRN, ...) counts, as before.

Until 2026-09-05 the check ignored DATE_TIME and LOCATION entirely, so a raw date or address
in an answer would have passed (TODO item 11). Tests: `tests/test_deid.py`,
`test_contains_phi_counts_identifying_dates_and_addresses`.
