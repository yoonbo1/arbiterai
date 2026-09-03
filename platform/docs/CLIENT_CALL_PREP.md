# Client call prep: discovery and demo

## Bring to the call
- Architecture whiteboard and a 5-minute walkthrough: document in → de-identified → indexed → question → cited answer → audit log.
- Live or recorded demo on synthetic data (under 3 minutes): upload one scanned discharge summary, ask two questions, show citations and the audit row.
- One-page shared-responsibility sheet derived from `HIPAA_CONTROLS.md`.
- Isolation tiers with rough pricing: shared (row-level), schema-level, dedicated. Have a per-document and per-query cost range.
- Draft BAA, or the statement that you sign one as their business associate.
- Phased plan: synthetic pilot → their de-identified sample → production, with exit criteria per phase.

## Questions to ask
- Document types, monthly volume, share of scans/faxes vs native PDFs.
- Where data lives today (EHR vendor, on-prem, cloud) and the transfer path: API, SFTP, EHR integration.
- Users and roles; SSO requirement.
- Residency and hosting requirements: on-prem only, specific cloud or region.
- Who reviews security (compliance officer), and whether SOC 2 / HITRUST is required.
- Definition of success: turnaround time, accuracy on named questions, staff hours saved.
- Retention and deletion expectations at contract end.

## Hard questions and answers
- Does our data train your model? No; explain the technical and contractual controls.
- Can another customer see our data? Key-derived tenant ID, Postgres row-level security, patient-level retrieval filter.
- What happens when it's wrong? Citations, validation node, human review, no automated clinical decisions.
- Who else touches the data? Every vendor listed, each with a BAA.

## Do not promise
- Certifications not yet held, accuracy numbers on their data, or timelines before seeing a document sample.

## After the call
- Recap email, shared-responsibility sheet, pilot proposal with scope and price.
- Request 20–50 de-identified sample documents to run the eval harness on their real formats.
