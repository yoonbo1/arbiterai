# From cited answers to structured clinical intelligence

What to build on top of ingestion once client documents are flowing, and in what order.
Written 2026-09-04 after reviewing Reveleer's public product pages and the current state of
this codebase. Not legal or coding advice; the regulatory notes are pointers for counsel and a
certified coder to confirm.

## 1. Where Arbiter stands next to Reveleer

Reveleer sells to health plans and value-based provider groups. Its stack, from its own
pages: medical record retrieval (chasing charts from providers), a clinical data
repository, an "Evidence Validation Engine" (EVE) that reads charts and links every
suggestion to source text, and workflow products on top of it: retrospective risk
adjustment (HCC coding with MEAT evidence), prospective risk adjustment (diagnosis and care
gaps surfaced at the point of care), HEDIS abstraction and audit, Care Gap Manager, RADV
audit packaging, and member/provider directory management.

The part of that stack Arbiter already has, and Reveleer describes as its differentiator,
is the evidence discipline: "EVE grounds every high-impact insight in real clinical
documentation, linking recommendations directly to source evidence" and "mandatory human
validation for coding and clinical decisions." That is exactly the citation gate, the
validation node, and the audit log in `worker/graph.py`.

What Arbiter has that Reveleer does not advertise: de-identification before any model call,
per-patient retrieval isolation enforced in the database, and a deployment that runs on
the customer's own hardware. Those are the reasons a hospital compliance officer would pick
a smaller vendor.

What Reveleer has that Arbiter should not chase: record retrieval as a service (a
logistics business), member engagement and outreach, provider directory validation, and
CMS submission. Those are operations products, not AI products.

The strategy this implies: **be the evidence engine.** Turn ingested documents into
structured, cited clinical facts, then sell workflows that consume those facts: chart
abstraction, condition validation with MEAT evidence, quality-measure evidence, audit
packets. Each of those is a query over the same fact table with a different rule set.

## 2. The foundation: structured clinical facts

Everything in section 3 depends on one addition to ingestion: after de-identification,
an `annotate` node that turns each page into rows in a `clinical_facts` table. Free text
stays where it is for retrieval and citations; facts are what rules and measures run on.

What a fact is:

| column | meaning |
|---|---|
| `kind` | problem, medication, lab, vital, procedure, allergy, immunization, referral, plan |
| `text` | the span as written, de-identified (`Follow up with Dr. <PERSON_2>`) |
| `normalized` | lower-cased canonical form (`metformin`) |
| `attributes` | jsonb: dose, route, frequency, value, unit, laterality, site |
| `assertion` | present, absent (negated), possible, conditional, historical, family |
| `section` | the note section the span sits in (Medications, Plan, Assessment) |
| `date_token` | the `<DATE_TIME_n>` token nearest the fact, restorable per document |
| `code_system`, `code` | ICD-10-CM, RxNorm, LOINC, SNOMED, or null when not mapped |
| `chunk_id`, `page` | the citation: which chunk and page the fact came from |
| `confidence` | 0 to 1 from the extractor; rules and measures set thresholds |
| `extractor` | which layer produced it (rules, ner, llm), for evaluation and drift |

Tenant and patient columns carry the same row-level security as `chunks`. Facts are
de-identified like everything else; only re-identification at the end of a query restores
names and dates, and only for the caller.

Three layers produce facts, cheapest first, and disagree loudly rather than silently:

1. **Section detection and rules.** Headings in clinical notes are strong signal. A
   sectionizer labels every line with its section; pattern rules catch structured lines
   such as `metformin 500 mg BID`, `HbA1c 8.1%`, `BP 140/72`. Fast, deterministic, and
   the thing most likely to be right on a discharge summary.
2. **Clinical named-entity recognition with assertion.** A biomedical NER model finds
   problems, drugs, and procedures in prose, and a context algorithm decides whether each
   is negated ("no evidence of pneumonia"), hypothetical, historical, or about a relative
   ("family history of CAD"). This is where "denies chest pain" stops becoming a chest pain
   diagnosis.
3. **LLM structured extraction with a validator.** The local model reads the page and fills
   a fixed JSON schema. It handles prose the rules cannot ("has been taking her water pill
   twice a day since the visit") but it can invent. Every LLM fact must be anchored to a
   verbatim span in the page, or it is dropped. The two cheaper layers act as the check.

Concept normalization (mapping "metformin" to an RxNorm code, "type 2 diabetes" to
ICD-10-CM E11.9) is what makes facts comparable across documents and is what every
feature below needs. The code sets have different licenses, in section 5.

The extraction stack, with the packages that were actually installed and tested on this
machine, is in Appendix A.

## 3. Features, in the order they pay for themselves

### 3.1 Evidence packets (chart abstraction)

The nearest extension of what exists. For a patient and a topic ("diabetes management",
"anticoagulation", "everything about the left knee"), assemble every relevant fact and
its cited page into one reviewable packet, grouped by section and date. An abstractor
opens the packet instead of the chart.

Why first: it needs only the fact table and the existing citation machinery, it is
valuable to every customer type (payer abstraction teams, CDI teams, medical-legal review),
and it is the demo that makes the rest credible. Reveleer's quality customers report the
value as abstractor time: "75% increase in abstractor efficiency."

### 3.2 Condition validation with MEAT evidence (retrospective risk adjustment assist)

For each documented condition, find the evidence that it was actively managed at an
encounter: Monitored (signs, progression), Evaluated (results reviewed), Assessed
(discussed, acknowledged), Treated (medication, referral, plan). Attach each piece of
evidence with its page citation, map the condition to ICD-10-CM and then to a CMS-HCC
category, and present the package to a human coder to accept or reject. Log the decision.

Two design rules that decide whether this product survives an audit:

- **It validates as much as it finds.** A diagnosis on a problem list with no MEAT evidence
  is a deletion candidate, not a code. OIG's February 2026 Medicare Advantage guidance
  flags "add-only" chart review as a compliance risk; Reveleer's own RADV page sells
  "identifying unsupported diagnoses before CMS review." Suggest both directions.
- **Nothing is ever submitted by the system.** Suggestions carry confidence and evidence; a
  credentialed coder decides. Every suggestion and every decision goes to `audit_log`.

Inputs that are public: ICD-10-CM code files (CMS/CDC, public domain) and the CMS-HCC
ICD-10-CM-to-HCC crosswalk and model software, including a Python version, published on
CMS's 2026 Model Software / ICD-10 Mappings page with no login. V28 is at 100% weight
for 2026 and maps 7,903 of 74,719 billable codes to an HCC. Note that RADV contract-level
extrapolation was paused by a court in September 2025 but audits continue.

### 3.3 Quality-measure evidence (HEDIS-style)

The same fact table answers "does this member have an HbA1c under 8.0 in the measurement
year?" or "is there a documented blood-pressure reading under 140/90?" Numerator and
denominator evidence, each with a page citation, exported for the customer's certified
HEDIS engine rather than reported by Arbiter ("engine-agnostic" is Reveleer's word for
the same choice).

Start with measures that are pure clinical data, where extraction quality is highest:
glycemic control, blood-pressure control, statin therapy, colorectal and breast cancer
screening documentation, immunization status. Reveleer supports "more than 40" measures;
five done well beats forty done badly.

Licensing: NCQA requires a commercial license to implement HEDIS measure specifications
in software sold to others. Internal non-commercial use is permitted without one. Either
license the specs, or ship a measure engine whose logic the customer supplies. Do not
publish measure logic in the product without the license.

NCQA has said digital-only HEDIS is the destination by 2030 and expanded ECDS reporting
in the MY 2026 specifications; that moves the value from annual abstraction to a pipeline
that structures notes as they arrive, which is what section 2 is.

### 3.4 Care gaps and the longitudinal record

Once a patient has more than one document, facts across documents form a timeline:
encounters, results over time, medication changes. Gaps fall out of the timeline: a
diabetic with no A1c in twelve months, a hypertensive with no reading since the last
visit, a referral with no consult note. Present them as a pre-visit summary for a
clinician or a worklist for a care manager, always with the evidence and always as a
question to a human, not an instruction.

Prerequisites this codebase does not have yet: an `encounters` table, document-date
extraction, and multi-document patients in the eval corpus. The reidentification fix in
`TODO.md` is also required, because dates in facts are tokens until restored.

### 3.5 Audit packets (RADV and internal)

For a sampled member and a list of HCCs, assemble the supporting evidence for each,
flag any HCC with no MEAT support, and produce a packet with page images and an
attestation trail. This is 3.2 run in reverse over a list the auditor supplies, plus
document rendering. Reveleer describes the deliverable as "CMS-ready digital packaging for
on-time, defensible audit response."

### 3.6 Cohort queries

The schema already reserves a `cohort` scope and the database policies already isolate
tenants. A population endpoint ("all patients with A1c above 9 and no statin") is a
query over facts with a separate credential scope and a separate audit action, so
population access never mixes with patient-care access. This is the feature the site's
"chart review and quality audits" pillar promises and the code does not have.

### 3.7 Suspecting

Reveleer's prospective product generates "suspect diagnoses" from "11,000 clinical
indicators": an elevated A1c with no diabetes diagnosis, an eGFR trend with no CKD
diagnosis. This is the highest-value and highest-risk feature on the list. It is a
diagnosis suggestion, which is close to clinical decision support, and your site and
terms say Arbiter "does not make clinical decisions." Build it last, present it as a
documentation query ("A1c of 9.1 on page 3 with no corresponding diagnosis; confirm or
dismiss"), and get counsel and a clinical advisor to sign off on the framing.

## 4. Data model additions

```
encounters      (id, tenant_id, patient_id, document_id, date_token, provider_token, kind)
clinical_facts  (as in section 2; indexes on (tenant_id, patient_id, kind, normalized))
code_maps       (system, code, display, hcc_v28, hcc_v24)   -- loaded from public files
fact_codes      (fact_id, system, code, confidence, method)
measure_defs    (id, name, version, logic jsonb, license_ref)  -- customer-supplied or licensed
measure_results (tenant, patient, measure_id, period, status, numerator_fact_ids, denominator_fact_ids)
suggestions     (tenant, patient, kind: hcc|gap|suspect, payload, evidence_fact_ids, confidence,
                 decision, decided_by_key_id, decided_at)      -- the human-in-the-loop record
```

All tables carry `tenant_id` and the same row-level-security policy as `chunks`.

## 5. Licensing of the code sets

| resource | who publishes | terms | can ship in the image? |
|---|---|---|---|
| ICD-10-CM codes and descriptions | CMS / CDC | public domain | yes |
| CMS-HCC crosswalk and model software (V28, incl. Python) | CMS | public download, no login | yes |
| RxNorm | NLM | free; full download needs a UMLS account; the RxNav lookup API is a cloud call and is off limits here | the downloaded files, yes; the API, no |
| LOINC | Regenstrief | free with registration and license acceptance; redistribution terms apply | after accepting terms, likely yes for embedded use; confirm |
| SNOMED CT (US edition) | NLM / SNOMED International | free in the US via UMLS affiliate license; per-organization | the customer, or you as affiliate; confirm before bundling |
| HEDIS measure specifications | NCQA | commercial license required for software; internal non-commercial use free | not without a license |

## 6. Guardrails that keep this a documentation product

- Every suggestion links to a verbatim span and a page. No span, no suggestion.
- A human with the right credential accepts or rejects. The system never submits, never
  writes to an EHR, never changes a code on its own.
- Every suggestion and decision is an `audit_log` row, so reviewer behaviour is itself
  reviewable. Reveleer calls this "mandatory human validation"; make it structural.
- Confidence is calibrated on a labelled set before it is shown, and drift is measured
  monthly against a held-out sample.
- The site and terms already say Arbiter does not provide medical advice or make clinical
  decisions. Features 3.2, 3.3, and 3.5 are documentation and coding support and fit that.
  Feature 3.7 is the one to take to counsel before building.

## 7. Sequencing

1. **Now.** The `annotate` node, the `clinical_facts` table, and an evidence-packet query.
   Extend the synthetic generator so the eval scores extraction (problems, meds with dose
   and frequency, labs with value, negation, family history).
2. **Next.** ICD-10-CM and HCC mapping from the public CMS files; MEAT evidence
   classification; the `suggestions` table with coder decisions; a coder review screen.
3. **Then.** Encounter reconstruction, multi-document patients, the first five quality
   measures with customer-supplied logic, care-gap worklists.
4. **Later.** RADV packet rendering, cohort endpoint, suspecting under advisor sign-off.

## Sources

- Reveleer solutions overview: https://www.reveleer.com/solutions
- EVE, Evidence Validation Engine: https://www.reveleer.com/technology/ai
- Retrospective risk adjustment: https://www.reveleer.com/solutions/risk-adjustment
- Prospective risk adjustment / clinical intelligence: https://www.reveleer.com/solutions/clinical-intelligence
- Quality improvement: https://www.reveleer.com/solutions/quality-improvement
- HEDIS audit and abstraction: https://www.reveleer.com/solutions/hedis-audit-abstraction
- Care Gap Manager: https://www.reveleer.com/solutions/care-gap-manager
- RADV audit: https://www.reveleer.com/solutions/radv-audit
- MEAT criteria and 2026 CMS/OIG context: https://www.raapidinc.com/blogs/simplify-hcc-coding-with-meat-criteria/
- CMS 2026 model software and ICD-10 mappings: https://www.cms.gov/medicare/payment/medicare-advantage-rates-statistics/risk-adjustment/2026-model-software-icd-10-mappings
- NCQA on using HEDIS measure specifications: https://www.ncqa.org/hedis/using-hedis-measures/
- HEDIS 2026 direction, ECDS and digital measures: https://linear.health/blog/hedis-measures-explained

## Appendix A. Extraction stack (verified on this machine)

_Filled in after the install and smoke tests; see below._
