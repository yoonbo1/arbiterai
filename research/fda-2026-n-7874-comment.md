# Comment on Docket FDA-2026-N-7874

**Considerations for the Regulation of Generative AI-Enabled Medical Devices: Discussion
Paper and Request for Feedback**

Submitted by Yoonbo Cho, independent engineer. Contact: hello@arbiterai.tech.
Supporting code, tests and evaluation results: https://github.com/yoonbo1/arbiterai
(Apache-2.0). Written record of the failures described below:
https://www.arbiterai.tech

---

## Scope of this comment, and its limits

I am one engineer. I am not a device sponsor and I have no product before the agency. I
build and publish an open reference implementation of a HIPAA-safe clinical document
pipeline: de-identification before any model call, retrieval scoped to a single patient and
enforced by the database, answers that must cite their source and clear a faithfulness
check, and an append-only audit log. It has never processed real patient information. Every
record it ships is synthetic.

What I can offer the agency is narrow but, I think, uncommon. I have published the cases
where my own evaluation was wrong, with the numbers, the code, and the tests that closed
them. Sections V.B and VI of the discussion paper ask what evidence should support a
benchmark used to gate a device, and whether a machine supervisor can be trusted to monitor
one after deployment. I have measured both failing. This comment describes those
measurements and what I believe they imply.

Everything below is measured on synthetic records. I say so each time, because the
distinction matters and Question 13 turns on it.

---

## Question 10, on construct validity and sponsor-developed benchmarks

> *"What evidence should support the construct validity of a benchmark used to gate device
> evaluation, and what role should sponsor-developed benchmarks play given potential
> concerns around independence and optimization to the test?"*

**A benchmark can be correctly implemented, faithfully reported, and still measure the
wrong thing. Sponsor self-assessment will not catch this, because the sponsor wrote the
construct.**

My de-identification harness measured whether each injected identifier survived into the
stored text. On its first run it reported recall of 0.967, with 116 of 120 identifiers
removed. The four survivors were physician surnames that are also common English words.
The number was arithmetically correct and the code did what it said.

The construct was wrong. Addresses were injected and checked as complete strings of about
forty characters. Only the city was ever recognised. A stored record read:

```
Address: 1049 Mitchell Lights Suite 075, <LOCATION_1>, AR 29101
```

The whole string did not survive, so the check counted a success. Counted by component
across twenty synthetic records, the ZIP code survived in fourteen, the street line in
seven, and the city in six. Component-level recall was approximately 0.81, not 0.967.

The gap was invisible to the metric and would have remained invisible to any review of
summary results. It became visible only when I reported a second, stricter metric beside
the first and read the surviving spans rather than the score.

**What I would suggest to CDRH.**

1. **Require the failures, not only the score.** A benchmark submission should include the
   items the device got wrong and the text of what survived, sampled and legible. A summary
   statistic cannot show a construct error; the artifacts can.
2. **Require at least two metrics of differing strictness for any composite identifier or
   composite claim**, with divergence between them treated as a finding to explain rather
   than a rounding difference.
3. **Treat the absence of a documented benchmark revision as a weak signal, not a strong
   one.** My harness reached 1.000 only after four revisions in a single day. A sponsor
   whose benchmark has never been wrong has more likely not looked hard than built it
   correctly. I would rather see a sponsor's history of corrections than a clean first
   number.
4. **On sponsor-developed benchmarks specifically:** they are unavoidable, because no
   public asset covers most intended uses. The mitigation is not independence of authorship
   but reproducibility. If the harness, the corpus, and the per-item results are published
   under a version and a canary, then a reviewer, a competitor, or a hospital can rerun it.
   Optimisation to the test is far harder to hide when the test is executable by others.

I would add one caution from the surrounding literature. A 2026 study of clinical
de-identification at Baylor and Texas Children's Hospital found 414 identifiers that the
reference annotation itself had omitted, all of those sampled confirmed on expert review,
and reported that systems which correctly redacted them were scored as having made errors.
**A benchmark can penalise the safer device.** Any gating threshold should be accompanied
by evidence about the quality of the reference standard, not only the device.

---

## Questions 12 and 13, on synthetic data

> *"Where synthetically generated inputs supplement real patient data, how should sponsors
> account for differences between the synthetic and real-world distributions...?"*
> *"What safeguards would mitigate the risk that synthetic data generated by models of the
> same class as the device under evaluation reproduces the very performance gaps the
> evaluation is intended to detect...?"*

My corpus is entirely synthetic and I rely on it heavily, so I want to state plainly what
it does and does not establish.

**The safeguard in Question 13 is real and it is cheap.** My records are generated by
templates and a name-and-address faker, not by a language model. No model that the pipeline
is evaluated against had any part in producing the evaluation data. I would suggest CDRH
consider this a minimum expectation rather than a good practice: **where synthetic
evaluation data is generated by a model, the sponsor should be required to state the
generating model and to justify why it does not share failure modes with the device.**
Where the generator is procedural, that fact is itself evidence and is trivial to document.

**But procedural generation buys independence at the cost of realism, and I can quantify
one instance.** My generated names are clean, correctly capitalised and drawn from a list.
Recall of 1.000 against them establishes almost nothing about names as they appear in real
records: misspelled, inconsistently cased, split across lines, abbreviated.

The clearest illustration in my own data came from degradation rather than distribution.
Half my corpus is rasterised, tilted, blurred and thresholded into pages with no text
layer, then read by optical character recognition, as a scan or fax would be. On one page
the recogniser read the label `MRN:` as `MAN:`. My identifier detector was anchored on the
exact label, so a seven-digit medical record number passed through untouched. Whole-string
recall on that corpus was 0.992 rather than 1.000, and the entire difference was one
character misread in a label.

That failure was undetectable on clean synthetic text and would have been undetectable on
clean real text. It appeared only because the corpus contained the degraded artifact that
the real workflow contains.

**What I would suggest.**

1. **Realism of the artifact should be assessed separately from realism of the content.**
   A corpus can have synthetic patients and still faithfully reproduce the scan, the fax,
   the form and the character error rate. For document-handling devices, the second matters
   at least as much as the first, and it can be achieved without any patient data.
2. **Synthetic evidence should be permitted to establish that a failure mode exists, and
   not permitted to establish that one is absent.** My results support the first claim
   strongly and the second not at all.
3. **On combining synthetic and clinical evidence into a single performance estimate:** I
   would counsel against a pooled point estimate. Reporting them separately preserves the
   information a reviewer needs. Where a combined estimate is unavoidable, the synthetic
   component's contribution should be stated and the pooling weights justified.
4. **On statistical meaningfulness,** one practical note. Evaluation items drawn from the
   same document or the same patient are not independent. Standard errors computed as
   though they were will be too narrow, materially so. Any acceptance criterion expressed
   as a threshold should specify the clustering unit.

---

## Questions 19 and 20, on postmarket monitoring and machine supervisors

> *"Please comment on whether the proposed approaches to postmarket monitoring can be
> facilitated by machine-based supervisory agents. What considerations, including the
> evaluation and reliability of the supervisory agent itself, should CDRH take into
> account?"*

**They can, and my system depends on one. It was also the least reliable component I
built, and its unreliability was invisible from its outputs.**

My pipeline will not return an answer unless a second model scores it as supported by the
retrieved source text. That supervisor is a small model asked for a single number between
zero and one, gated at 0.7.

On one evaluation run it rejected five of forty answers. All five were correct. All five
were the same question. Reproducing the calls exactly, the score depended on where the
citation marker sat:

| Answer text | Score |
|---|---|
| `The most recent HbA1c is 9.0% [7].` | 0.0 |
| `The most recent HbA1c is 9.0%. [7]` | 1.0 |
| `The most recent HbA1c is 9.0%.` | 1.0 |
| `HbA1c 9.0% [7]` | 1.0 |

The content is identical. The supervisor was deterministic, so this was not sampling
noise, and it was reproducible on demand.

Three consequences worth the agency's attention.

**First, the escalation did not help and could not have.** A failed check triggered a retry
against a larger tier. On my hardware that tier was configured to the same model at the
same temperature, so it returned the same verdict at roughly eight times the cost, and a
correct answer was discarded. A supervisory architecture can contain a review step that is
structurally incapable of changing an outcome. I would suggest that where a monitoring
scheme includes escalation or adjudication, the sponsor be asked to demonstrate that the
escalation path is capable of reaching a different conclusion.

**Second, the supervisor was unaccounted for.** Its calls were roughly half of all model
traffic in the system and were not counted at all, because the function discarded the usage
figures. Corrected, the measured token consumption of a run went from 13,055 to 24,969.
Any postmarket monitoring programme whose cost or load is used to argue feasibility should
account for the monitor's own consumption.

**Third, and most important, the supervisor's output looked healthy.** It produced a
well-formed number in the expected range, consistently, for every input. Nothing in its
output distribution indicated a defect. It was caught only because I compared its verdicts
against answers I had independently established to be correct.

**A second failure, found on 8 September 2026 while expanding this harness, is worse than the
first.** I added questions whose correct answer is a negation: the note records a condition in
the family history, and the question asks whether the patient has it. The supervisor rejected
almost all of them. Isolating it, with the source text held identical and each case run three
times at temperature zero:

| Answer given | Truth | Score | Gate |
|---|---|---|---|
| "Stroke appears in the family history for this patient." | correct | 1.00 | passes |
| "The record documents a family history of stroke." | correct | 1.00 | passes |
| "No, the patient does not have stroke. Stroke is documented as family history." | correct | 0.00 | rejected |
| "The patient does not have stroke." | correct | 0.00 | rejected |
| "Yes, the patient has stroke." | **wrong** | 0.00 | rejected |
| "The patient was diagnosed with stroke during this admission." | **wrong** | 0.00 | rejected |
| "The patient has a family history of breast cancer." | **wrong** | 0.00 | rejected |

The supervisor blocked every incorrect answer, which is the property one wants. It also blocked
half the correct ones, and it assigned a correct negation exactly the same score as a
fabrication. The signal it discriminates on is grammatical polarity, not truth. A claim stated
positively can be matched against the source; a claim stated negatively cannot, because the
absence of a fact is not written in the text.

The consequence for a monitoring programme is that the two outcomes are indistinguishable from
outside. A rejected answer looks the same whether the device was wrong or the device was right
in a form the supervisor cannot verify. In my run of 346 questions, that mechanism silently
discarded 18 of 20 correct answers in one category while the aggregate accuracy still read
0.90.

I would draw the agency's attention to this being a known and studied property rather than an
artifact of my system. Published work in 2026 reports that language-model judges detect added
or altered content at 0.79 to 0.94 discrimination and detect omissions at 0.50 to 0.63, which
is near chance. A supervisor built to verify presence should not be assumed to verify absence,
and clinical documentation is full of claims about absence.

**What I would suggest for supervisory agents.**

1. **A supervisor should be validated against human judgment before it is relied upon, on
   the specific task and format it will supervise**, and the agreement statistic should be
   reported alongside the performance of the device it supervises. Reported agreement
   between model juries and clinicians in published clinical benchmarks is currently low
   enough that this is not a formality.
2. **Format sensitivity should be tested explicitly.** Semantically identical outputs
   differing only in punctuation, ordering or citation placement should receive the same
   verdict, and a sponsor should be able to show that they do.
3. **Reliability and validity should be reported separately.** A supervisor can be highly
   reproducible and consistently wrong. Mine was.
4. **The monitoring programme should be re-validated whenever the supervising model
   changes**, on the same footing as the device itself. In practice the supervisor is a
   second device, and it is currently invisible.

---

## One general observation

The discussion paper asks in Section VI whether greater postmarket monitoring could justify
accepting more premarket uncertainty. I think that trade is sound, and I would add one
condition drawn from my own experience.

Every failure described above was found by an automated harness and confirmed by reading
the artifacts. None was found by inspecting summary metrics, and two of them were actively
concealed by summary metrics that were computed correctly. If postmarket monitoring is to
carry weight it was not previously asked to carry, then what is retained and reviewable
matters more than what is reported. My recommendation is that a monitoring programme be
expected to preserve per-item inputs, outputs, and the supervisor's verdicts in a form that
someone other than the sponsor can inspect, rather than aggregate performance summaries
alone.

I am glad to supply any of the underlying data, code or results, and to answer questions.

Respectfully submitted,

**Yoonbo Cho**
hello@arbiterai.tech
