# The free plan
**2026-09-08.** Constraint: no spending. No API keys, no rented compute, no hardware.
Everything below runs on the M4 with the local 7B model, or on public data, or costs
nothing but an application form.

The good news is that this barely narrows the plan. The disk worry was wrong: 50,000
synthetic documents need 1.4 GB against 63 GB free. The API sweep across frontier models
was the only line item that needed money, and it was never the interesting part. The
interesting part is statistics, and statistics is free.

---

## What the research actually pointed at

Across every area surveyed, the field bottoms out in the same place. Judges are unreliable
raters and nobody measures it. Benchmarks report intervals that are too narrow. Reference
annotations are wrong. Nobody clusters standard errors. The scarce skill is not building
evaluations, it is producing a defensible number from a biased grader, and that is done
with a laptop and care rather than a cluster.

So the free plan is not a reduced version of the paid plan. It is the same plan with the
part that needed money removed, and that part was the least novel.

---

## 1. The FDA comment. Free, and it expires 19 October

Drafted at `research/fda-2026-n-7874-comment.md`. It answers questions 10, 12, 13, 19 and
20 with measurements already published: the recall of 0.967 whose construct was wrong, the
identifier that survived because optical character recognition misread its label, and the
supervisory model that scored identical facts 0.0 or 1.0 depending on punctuation.

Submit at https://www.regulations.gov/docket/FDA-2026-N-7874

Cost: nothing. Permanent, attributed, publicly citable federal record.

---

## 2. Free applications, in order

| What | Why it matters | Link |
|---|---|---|
| **Anthropic Fellows** | Stipend plus compute. ML Systems and Reinforcement Learning track. Open now. | https://job-boards.greenhouse.io/anthropic |
| **TPU Research Cloud** | Over 1,000 Cloud TPUs, no affiliation required, renewable. Condition is publication, which is the plan anyway. Synthetic corpus only, never patient data. | https://forms.gle/uwWjUewyxZ5okL3W7 |
| **An institutional affiliation** | The single gating check for the federal compute programmes, which reject personal email addresses outright. A guest or visiting-researcher status converts the whole locked column and costs one email. | — |

---

## 3. Free engineering, ranked

Every item runs locally, produces a publishable result, and is unclaimed. Ordered by value
over effort.

### 3.1 A leak rate with a confidence interval that survives scrutiny

The de-identification literature has exactly the structure that prediction-powered
inference was built for: a cheap detector that labels everything, and expensive human
adjudication on a small subset. It has never been applied there. The method returns a valid
interval **despite** the detector being biased, and it cannot do worse than ignoring the
detector.

The setup is roughly 100 to 300 human-adjudicated spans against the full detector output.
Then benchmark the estimate three ways, against measurement-error correction and against
constrained maximum likelihood, on a span-level task where nobody has compared them.

The output is the sentence a compliance office actually wants and that nobody in this field
can currently produce: *leak rate below some threshold at 95% confidence, using this many
adjudicated spans and a detector with this measured error profile*.

Cost: adjudication time. That is also the moat.

### 3.2 Cluster the standard errors, then discover how much that changes

Evaluation items drawn from the same note are not independent, and neither are notes from
the same patient. Published work in this area reports F1 to three decimal places with
errors computed as though every span were an independent draw. On general benchmarks the
correction has been measured at up to three times.

Here the nesting is three deep: spans within notes, notes within patients, patients within
institutions. Measuring that design effect on a public corpus, and showing which published
comparisons stop being significant under it, is cheap and load-bearing.

The sample sizes involved are also small enough that the usual approximation is known to
understate uncertainty badly, so the intervals should be computed a second way as a check.

### 3.3 Attack the judge

A published result shows that generative reward models return false positives at rates
above 80% when handed bare punctuation or a generic reasoning opener. Running that against
the faithfulness judge takes an afternoon and either finds a live vulnerability or produces
a negative result worth stating.

The companion probe is equally cheap: train a classifier on rubric or prompt text alone,
with no access to the answer being judged, and see whether it predicts the judge's verdict.
If it does, the judge is partly grading itself.

### 3.4 Determinism on Apple Silicon

The definitive work on temperature-zero nondeterminism showed that 1,000 completions from
one model produced 80 unique outputs, and traced it to kernels whose numerics depend on
batch size. That work is entirely on NVIDIA hardware.

Nobody has published the equivalent for Metal. How many unique completions out of 1,000, as
a function of batch size, thread count and context length, and whether the local kernels
are batch-invariant. The hardware is on the desk, the model is already installed, and no
lab will produce this because none of them ship on Macs.

### 3.5 Audit a public leaderboard's confidence intervals

A widely cited agent leaderboard publishes a field labelled as a 95% half-width. For its
top entry, 192 successes in 330 trials:

| Quantity | Value |
|---|---|
| Point estimate | 58.18% |
| Standard error | 2.72 pp |
| Correct 95% half-width | 5.32 pp |
| Published half-width | 2.79 pp |
| Published divided by one standard error | 1.03 |

The published figure is almost exactly one standard error, not the 1.96 that a 95% interval
requires. And because those 330 trials are 66 tasks run five times each, the trials are
clustered, so the honest interval is wider still: between 7 and 11 percentage points
depending on how correlated repeated attempts at the same task are.

The top two entries on that leaderboard differ by 0.30 percentage points.

**This is a lead, not yet a finding.** The numbers above come from a research summary rather
than from the raw payload read directly, and the estimator behind the published column is
not documented. Verifying it means fetching the leaderboard data and recomputing every
entry. That is a few hours against public data and costs nothing.

### 3.6 Estimate how wrong the reference annotations are

A 2026 study found 414 identifiers that a gold standard had omitted, all of those sampled
confirmed genuine on expert review, and systems that correctly caught them were scored as
having erred. The same pattern was found on a general benchmark, where verifying 2,500
items left 668 that passed expert review unchanged.

Sampling spans from a public corpus, adjudicating them, estimating the error rate with an
interval, and re-scoring published systems against corrected labels is unglamorous and
nobody will fund it. It is also the thing that would make every downstream number mean
something.

---

## 4. What free does rule out, honestly

Comparing frontier models against each other needs either paid keys or free tiers with
rate limits that may forbid publishing named comparisons. Until that is resolved, the
benchmark compares what runs locally: rule-based pipelines, the recognizer package, the
local models already installed. That is enough for every item in section 3, none of which
depends on a frontier model.

Anything needing a GPU cluster was already out of reach and remains so, and none of the
work above wants one.

---

## 5. Order of operations

1. Review and file the FDA comment. It has the only hard deadline.
2. Send the two applications. Ten minutes each.
3. Start on the leak rate with a real interval, because it is simultaneously a paper, a
   product feature, and the thing that makes the benchmark defensible later.
4. Take the cheap wins in parallel: the judge attack and the leaderboard audit are each
   under a day and either could produce a result before the FDA deadline.
