# Test data: what exists, what we may use, and how to reach a million documents

Researched and verified 2026-09-04. Two agents checked every figure against the publisher's
own page, actually ran Synthea on this machine, and benchmarked pgvector at a million
vectors. Anything that could not be confirmed on an official page is marked unverified.
Not legal advice; the license notes are pointers for counsel.

The one-line answer: **a million-plus documents of real de-identified clinical text exists
and is obtainable, but only through PhysioNet's credentialing; a million synthetic
documents can be generated on this machine in an afternoon but would need an external
disk and about a week of ingestion; and no corpus of any size can be used for evaluating
a commercial product without reading its license first.**

## 1. The two constraints that decide everything

**Real PHI is off the table**, by your own rule and by law. That leaves de-identified
real text under its agreement, or synthetic text.

**This Mac has 14 GB free.** Ingesting a document costs roughly 3 chunks of 2.4 KB in the
table plus 2 KB each in the vector index, so a million one-page documents is about 13 GB
of Postgres before the PDFs themselves. The benchmark below was run in a throwaway
container and cleaned up. A million-document run on this machine needs an external SSD,
or a generate-ingest-delete loop in batches.

## 2. Real de-identified clinical text

### 2.1 The million-scale sources: MIMIC, via PhysioNet

| corpus | notes | patients | note types | how PHI was removed |
|---|---|---|---|---|
| MIMIC-IV-Note v2.2 | **2,653,149** | 145,915 with discharge summaries, 237,427 with radiology | 331,794 discharge summaries + 2,321,355 radiology reports | rules plus neural model; every PHI span is `___`; dates shifted into 2100 to 2200 |
| MIMIC-III v1.4 NOTEEVENTS | **2,083,180** rows | 46,520 | 15 categories: nursing/other 822k, radiology 522k, nursing 223k, ECG 209k, physician 141k, discharge summaries ~60k, others | dictionary and regex; placeholders like `[**Patient Name**]`; dates shifted; ages over 89 shown as 300 |
| MIMIC-CXR v2.1.0 | 227,835 reports | 65,379 | chest X-ray reports | `___`; whether these overlap MIMIC-IV-Note radiology is not stated |

One hospital (Beth Israel Deaconess, Boston), ICU-heavy for MIMIC-III, hospital-wide but
only two note types for MIMIC-IV. The two releases overlap for 2008 to 2012 and cannot be
joined by patient id, so a per-patient retrieval test must live inside one release.

**Either MIMIC-IV-Note alone or MIMIC-III alone clears one million.** MIMIC-IV-Note is the
better choice: newer de-identification, hospital-wide, and radiology alone is 2.3 million.
Discharge summaries average about 2,270 tokens, so rendered to PDF they are three to six
pages each: the 331,794 discharge summaries are roughly 1.2 million pages of dense clinical
prose on their own.

**How to get it.** Everything is per person, not per company:

1. Create a PhysioNet account and complete the CITI "Data or Specimens Only Research"
   course (affiliate as MIT to avoid fees; upload the completion report, not the
   certificate).
2. Submit a credentialing application with a research description and a reference.
   Institutional email is "not required, but helpful". PhysioNet publishes no policy on
   applicants from companies; that is unverified and worth an email to them first.
3. Sign the data use agreement separately for each dataset.
4. Turnaround is quoted as several business days to two weeks.
5. Every person who touches the data must be credentialed. "Sharing data within teams or
   classes is not permitted." That includes contractors, CI runners and shared buckets.

**The rules that matter for this pipeline, quoted from PhysioNet.** The license limits
use to "the sole purpose of lawful use in scientific research and no other" and says
nothing about commercial use either way; get a written answer before relying on MIMIC for
product acceptance tests. On models: "Local LLM models can be used without restrictions,
but there are limitations when using API services", and "Use locally deployed LLMs to
maintain full control over the data." Consumer services such as ChatGPT and the OpenAI API
are explicitly prohibited; the 2025 update allows certain enterprise services only after
you verify zero data retention, no training on the data, and no human review, and says
PhysioNet "cannot verify the data practices of external services." **A 7B model, Tesseract
and Presidio running on your own hardware are squarely inside the rules.** Any residual PHI
you find must be reported to PhysioNet, not kept. Re-identification attempts are forbidden.

**What MIMIC can and cannot test here.** Because the PHI is already replaced with `___`
or bracketed tags, a second de-identification pass finds almost nothing, so **MIMIC cannot
measure de-identification recall**. It can measure precision, meaning over-scrubbing of
clinical terms, which is the failure we actually observed (`Foley catheter` scrubbed as a
name). It is the right corpus for extraction and assertion quality, retrieval, and scale.
The dates in 2100 to 2200 will trip any date validator. The placeholders must be stripped
or mapped before named-entity recognition, or the bracket tags get tagged as organizations.

### 2.2 The gold-standard sets for de-identification recall: n2c2 and i2b2

These are small but carry realistic surrogate identifiers with span annotations, which is
exactly what recall measurement needs:

| corpus | documents | what it gives |
|---|---|---|
| 2006 de-identification | 889 discharge summaries | PHI spans |
| 2014 de-identification and heart disease | 1,304 records, 296 patients | PHI spans, dates shifted by one corpus-wide offset |
| 2016 psychiatric intake | 1,000 records | PHI spans, false names from lists |
| 2010 concepts, assertions, relations | 1,748 documents | problems, treatments, tests, and assertion status |
| 2018 medications and adverse events | 505 MIMIC-III discharge summaries | medications with dose, route, frequency |
| 2022 medication events | 500 notes | 9,013 medication mentions |

Roughly 10,000 to 15,000 unique documents across all tasks. Access is a per-person data
use agreement through Harvard DBMI, human-reviewed, no published turnaround, no
redistribution even as test fixtures. A separate commercial-user agreement exists on their
site but returned an error to automated access, so its clauses are unverified.

### 2.3 Open sets and what their licenses actually permit

| corpus | size | license | usable to evaluate a commercial product? |
|---|---|---|---|
| PMC-Patients v2 | 250,294 patient summaries from published case reports | CC BY-NC-SA | **No.** NonCommercial turns on the use, and evaluating something you sell is a commercial use. |
| Asclepius synthetic notes | 158,114 GPT-rewritten discharge summaries | CC BY-NC-SA | No, and they contain no identifiers, so they test nothing about de-identification. |
| MedAlign (Stanford) | 46,252 real notes, 275 patients | data use agreement, industry applicants accepted | Yes for evaluation; training forbidden; no commercial APIs. |
| MTSamples | 5,043 transcribed sample reports | no license, educational permission only | Unclear. |
| MACCROBAT, MTS-Dialog, ACI-Bench, PriMock57 | 200 / 1,700 / 207 / 57 | CC BY 4.0 | Yes. Small. |
| MEDDOCAN, CodiEsp (Spanish), GraSCCo (German) | 1,000 / 1,000 / 57 | CC BY 4.0 | Yes; not English. |

Adding every permissive and non-commercial set together reaches about 480,000 documents,
most of it non-commercial. **There is no path to a million documents of real text without
PhysioNet.**

### 2.4 Scanned-document sets for the OCR router, not medical

| corpus | pages | license | note |
|---|---|---|---|
| RVL-CDIP | 400,000 scanned pages, 16 classes including forms, letters, handwritten | tobacco-litigation terms; internal use only | contains real SSNs and correspondence; treat outputs as sensitive |
| IIT-CDIP | about 7 million documents, roughly 1.4 TB; page count not published | NIST, no US copyright | the parent of RVL-CDIP; the old ir.nist.gov host is gone, download from data.nist.gov |
| DocLayNet | 80,863 pages, hand-annotated layout | CDLA-Permissive | financial, legal, patents, manuals |
| PubLayNet | about 364,000 pages | CDLA-Permissive | born-digital scientific; IBM's official host is dead and the community mirror is partial |
| NIST SD2 and SD6 | 5,590 and 5,595 tax-form pages | NIST | synthesized and hand-printed forms |

RVL-CDIP is the right corpus to validate that the text / OCR / vision router does the
right thing on handwriting, forms, and bad scans at scale. It is not clinical, and it
must never ship in a product or a fixture. No public dataset of medical faxes exists.

## 3. Synthetic text at scale: Synthea, measured on this machine

Synthea (MITRE, Apache 2.0, last release August 2026) generates whole patient histories.
It was run here with Java 21 installed for the purpose.

| run | records | wall time | output |
|---|---|---|---|
| 100 patients | 107 | 12.6 s | CSV 66 MB, text records 11 MB, templated notes 8 MB |
| 1,000 patients | 1,152 | 33.4 s | CSV 835 MB, per-encounter text 438 MB across 68,241 files |

Steady state is **50 records per second, so a million patients is six to nine hours**,
in batches of ten to fifty thousand because memory grows with population. Disk is the
problem: 742 KB of CSV per patient, 58% of it claims tables you can exclude, still 310 GB
per million. FHIR output is 3.6 MB per patient, out of the question here.

What Synthea gives you for free that matters: names (with numeric suffixes like
`Adela471 Romero158`), birth dates, synthetic SSNs, street addresses, provider names and
phones, and per patient about 59 encounters, 37 conditions, 12 distinct medications,
793 observations, one inpatient stay on average. What it does not give: narrative prose.
The optional "clinical note" exporter is a fixed template ("No complaints." on every note,
SNOMED display strings verbatim). An OHDSI evaluation found its demographics skewed and
its medication data "unreliable without external modification."

### The recipe

The existing generator already accepts Synthea's `patients.csv`. Extending it to read the
other tables gives about **20 documents per patient**: one discharge summary per inpatient
stay, one ED note per emergency visit, one lab report per encounter with results (about
14), a medication list, a referral letter. So:

| step | number |
|---|---|
| patients needed for 1M documents | about 49,000; generate 60,000 for margin |
| Synthea time | 25 to 35 minutes |
| documents, pages | 1.23 million, 1.5 million |
| clean PDFs on disk | about 6 GB |
| scanned variant for half of them, at the fixed 13 KB per page | about 10 GB |
| Postgres, at 3 chunks per page | about 11 GB table plus 9 GB index |

The scan-size fix landed today: the generator was embedding a decoded bitmap, so each
"scanned" page was 2 MB and a million of them would have been 2 TB. They are now 13 KB.

**Ingestion time is the real cost.** Measured on one worker here: 1 s per clean page,
2 s per OCR page, 36 ms per page for clinical extraction, 10 to 30 ms per chunk to embed.

| configuration | wall time for 1.23M documents |
|---|---|
| one worker on this Mac, half scanned | about 28 days |
| one worker, no scanned variant | about 19 days |
| four workers on this Mac | about 7 days |
| sixteen workers on a GPU box with GPU OCR and batched embeddings | about 15 hours |

The OCR share is the biggest lever; halving it saves more than any other change.

Extensions the generator needs, in order: read all Synthea tables and join on encounter;
document types with their own templates and a `doc_type` field; identifier injection with
gold character offsets and Safe Harbor category for every span, including dates in several
surface forms and relative dates as hard negatives; gold facts with SNOMED, RxNorm and
LOINC codes straight from the CSV columns; layout diversity so the vision router has
something to route; sharded output and a JSONL manifest; a multiprocess flag.

## 4. What a million synthetic documents proves, and what it does not

It proves throughput and queue behaviour, isolation at scale, storage growth, retrieval
latency against millions of chunks, index build and maintenance cost, router shares, and
de-identification recall on identifiers of known form. It does not prove de-identification
recall on real clinical language, extraction quality on real negation and temporal
phrasing, or anything about the messiness of real records. Those need MIMIC and n2c2.

The vector index, benchmarked here in pgvector 0.8.6 at 384 dimensions:

| scale | build time | index size | per vector | top-10 query |
|---|---|---|---|---|
| 100,000 | 22 s | 195 MB | 2,048 B | |
| 1,020,000 | 4 min 40 s | 1,992 MB | 2,048 B | 10 to 16 ms |
| plus 20,000 inserts, one connection | 82 s, about 4 ms each | 2,031 MB | | |
| 100,000 as half-precision | 13 s | 112 MB | 1,170 B | |

At 30 million chunks the index alone is about 60 GB and no longer fits this machine's
memory; half-precision vectors halve that. One design consequence for a multi-tenant
system: a single global index with a tenant filter loses recall for small tenants once
the filtered scan hits pgvector's scan limit. Partition chunks per tenant, or give each
tenant a partial index, and load-test exactly that with the synthetic corpus.

## 5. Recommendation

1. **Start the PhysioNet credentialing today.** It is the only route to a million real
   documents, it takes one to two weeks, and the license question about commercial
   evaluation should be asked in writing at the same time. Request MIMIC-IV-Note first.
2. **Apply for the n2c2 2014 and 2016 de-identification sets.** Small, but they are the
   only way to measure recall on realistic identifiers, which MIMIC cannot do.
3. **Build the Synthea corpus at 60,000 patients now, on an external SSD**, and run the
   scale tests it is good for: throughput, isolation, index growth, the tenant-partition
   question. Ingest in batches; do not try to hold the whole thing on the internal disk.
4. **Use RVL-CDIP, internally only, to validate the router** on real scans of forms and
   handwriting.
5. **Do not use the CC BY-NC sets** (PMC-Patients, Asclepius) for anything tied to the
   product without the licensor's written permission.

## Sources

PhysioNet: https://physionet.org/content/mimic-iv-note/2.2/ ,
https://physionet.org/content/mimiciii/1.4/ , https://physionet.org/content/mimic-cxr/2.1.0/ ,
https://physionet.org/about/faqs/ , https://physionet.org/news/post/llm-responsible-use/ ,
https://physionet.org/news/post/gpt-responsible-use , https://mimic.mit.edu/docs/faq/how-to-get-access.html ,
https://physionet.org/content/labelled-notes-hospital-course/1.2.0/ .
n2c2 task papers: https://pmc.ncbi.nlm.nih.gov/articles/PMC1975792/ (2006),
https://pmc.ncbi.nlm.nih.gov/articles/PMC4978170/ (2014), https://pmc.ncbi.nlm.nih.gov/articles/PMC5705537/ (2016),
https://pmc.ncbi.nlm.nih.gov/articles/PMC3168320/ (2010), https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/ (2018).
Open sets: https://github.com/zhao-zy15/PMC-Patients , https://huggingface.co/datasets/starmpcc/Asclepius-Synthetic-Clinical-Notes ,
https://github.com/som-shahlab/medalign/ , https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.en ,
https://wiki.creativecommons.org/wiki/NonCommercial_interpretation .
Document images: https://adamharley.com/rvl-cdip/ , https://data.nist.gov/rmm/records/mds2-2531 ,
https://github.com/DS4SD/DocLayNet , https://arxiv.org/abs/2306.12550 .
Synthea: https://github.com/synthetichealth/synthea , https://github.com/synthetichealth/synthea/wiki/CSV-File-Data-Dictionary ,
https://academic.oup.com/jamia/article/25/3/230/4098271 ,
https://www.ohdsi.org/wp-content/uploads/2024/10/41-Wagner-Evaluating_Synthea-Clair-Blacketer.pdf .
pgvector: https://github.com/pgvector/pgvector , https://www.crunchydata.com/blog/hnsw-indexes-with-postgres-and-pgvector .
