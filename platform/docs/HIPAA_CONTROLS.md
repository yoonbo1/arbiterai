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
| De-identification | Presidio + MRN recognizer, leak check on outputs | Measure recall on n2c2/i2b2; tune thresholds; human review sample |
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
