# Distribution drafts (2026-09-05)

Everything here is ready to paste. Order: LinkedIn headline and About first (they are what a
reader lands on after any post), then one post every two or three days, Tuesday to Thursday,
mornings US Eastern. On LinkedIn, put the link in the first comment if you want reach; the
text below works either way. On Hacker News, submit the URL with the title exactly as written
and post the comment as the first reply; one submission per day at most, never two of your
own at once. Save "Show HN" for last, after the four posts, so the repo has a CI badge and
some stars by then.

## LinkedIn profile

**Headline** (220 characters max):

> AI engineer, healthcare · Built Arbiter AI, an open reference implementation of HIPAA-safe document AI, with the evals to prove it · arbiterai.tech

**About** (paste as is):

> Arbiter AI is an open reference implementation of HIPAA-safe document AI: de-identification before any model call, cited and verified answers, database-enforced patient isolation, and an append-only audit trail — with the evaluation harness that proves each of those properties holds.
>
> I built it to have a public, checkable answer to "what does a correct clinical document pipeline look like?". Everything is measured: de-identification recall per identifier component, answer accuracy against gold questions, cross-patient leak count, judge faithfulness, latency, tokens and cost. The failure modes I found on the way are written up as post-mortems, each linking the code and the test that closed it.
>
> Code: github.com/yoonbo1/arbiterai · Site: arbiterai.tech · Contact: hello@arbiterai.tech

## LinkedIn posts (each under 150 words)

### 1. spaCy redacted "daily"

> My first eval run on a clinical document pipeline scored 0.575 on 40 gold questions. Twelve misses were "list the discharge medications", and eleven of those had every drug and dose right but no frequency.
>
> The stored chunk read: sertraline 50 mg <DATE_TIME_2>.
>
> spaCy's DATE label, which Presidio's date recognizer inherits, had tagged "daily" in 15 of 19 documents and "nightly" in 4 of 8. Safe Harbor removes dates tied to a person, not dosing frequencies.
>
> The fix is a filter that keeps a date hit only if it contains a month, a numeric date, a year or an ordinal. Two tests pin it. The same audit found MRNs never firing (score 0.4 against a 0.5 threshold), phone extensions missed, and four clinician surnames that are common words.
>
> Accuracy after: 0.95. Full write-up, with the code and the tests:
> https://www.arbiterai.tech/blog/spacy-redacted-daily.html

### 2. The flattering recall metric

> My de-identification recall read 0.967. ZIP codes had survived in 14 of 20 documents.
>
> The harness checked whether each injected identifier survived as a whole string. Addresses are 40 characters, and only the city was ever tokenized, so "1049 Mitchell Lights Suite 075, <LOCATION_1>, AR 29101" counted as a success.
>
> Counted by component: ZIP in 14 of 20, street line in 7 of 20, city in 6 of 20. Real recall about 0.81.
>
> Three changes: a strict per-component metric reported next to the flattering one, a US street-address recognizer (Presidio ships none), and merging overlapping spans into their union instead of keeping the best one. Over-redaction is recoverable; under-redaction is a breach.
>
> Twenty synthetic records, 40 gold questions, under three minutes a run, so four iterations fit in a day: 0.967 to 1.000. The i2b2 2014 number is next.
> https://www.arbiterai.tech/blog/deid-recall-flattering-metric.html

### 3. The 7B judge and the citation

> My faithfulness judge scored the same correct answer 0.0 or 1.0 depending on where the citation sat.
>
> "The most recent HbA1c is 9.0% [7]." scored 0.0. "The most recent HbA1c is 9.0%. [7]" scored 1.0. Same 7B model, temperature 0, fully deterministic.
>
> Five of 40 correct answers were rejected. Each one escalated to the "large" tier, which on my machine is the same model, got the same verdict, and cost 8× before being discarded.
>
> Second finding from the same afternoon: the judge's calls were about half of all model traffic and were never counted. The function threw the usage away.
>
> Fix: strip citation markers before judging, return the token count, meter it. Honest token counts per run went from 13,055 to about 24,000. Validation failures: zero.
>
> What is still open, and why a single number from a 7B model is the wrong shape for this job:
> https://www.arbiterai.tech/blog/7b-judge-citation-placement.html

### 4. The Postgres superuser

> The tenant isolation my README promised did not exist.
>
> Row-level security was enabled on every PHI table, with a policy on the tenant id, and an app role was created for it. But the gateway and worker connected as the database owner. Postgres exempts owners and superusers from RLS, silently. Every policy was ignored. Any tenant's key could read any job by id.
>
> Fix: both services connect as the app role; a REVOKE on the audit log, because the blanket GRANT had handed it UPDATE; tenant context set transaction-locally so pooled connections never leak it; and the eval harness refuses to run as a role that bypasses RLS.
>
> Probes: key B on tenant A's job → 404. Wrong tenant context → zero rows. Cross-tenant insert → policy violation.
>
> Isolation must not depend on application code being bug-free. That is only true if RLS applies to the role the application uses.
> https://www.arbiterai.tech/blog/postgres-superuser-bypasses-rls.html

## Hacker News

Submit as a link. Titles verbatim (HN edits titles that editorialize; these are the posts' own).

| order | title | URL |
|---|---|---|
| 1 | The services were connecting as the Postgres superuser, which silently bypasses RLS | https://www.arbiterai.tech/blog/postgres-superuser-bypasses-rls.html |
| 2 | spaCy redacted the word "daily" and broke 11 of 12 medication lists | https://www.arbiterai.tech/blog/spacy-redacted-daily.html |
| 3 | Our de-id recall read 0.967 while ZIP codes survived in 14 of 20 documents | https://www.arbiterai.tech/blog/deid-recall-flattering-metric.html |
| 4 | The 7B judge scored identical facts 0.0 or 1.0 depending on where the citation sat | https://www.arbiterai.tech/blog/7b-judge-citation-placement.html |
| 5 | Show HN: Arbiter – open reference implementation of HIPAA-safe document AI, with evals | https://github.com/yoonbo1/arbiterai |

The Postgres one goes first: it is the most general (anyone running RLS can hit it) and the
one most likely to reach the front page.

**First comment, posts 1 to 4** (adjust the first sentence to the post):

> Author here. This is one of four post-mortems from building an open reference implementation of a HIPAA-safe clinical document pipeline (de-identification before any model call, cited and verified answers, RLS-enforced patient isolation, append-only audit). Everything runs locally on a 7B model; no cloud APIs. All numbers are on synthetic records, which the post says explicitly; the i2b2 2014 run is pending credentialed access. Code and tests are linked from the post. Happy to answer questions about the harness or the recognizers.

**Show HN text** (the text field, under the link):

> I built this to have a public, checkable answer to "what does a correct clinical document pipeline look like?". It is one engineer's reference implementation, not a product: no hosted service, no BAA, synthetic data only.
>
> What it does: text extraction with OCR routing, Presidio de-identification with a reversible per-tenant map, clinical fact extraction with assertion, pgvector retrieval hard-filtered on (tenant, patient) on top of row-level security, a local 7B answer with chunk citations, a validation gate (citation required, faithfulness ≥ 0.7, PHI-leak check), re-identification for the caller only, and an append-only audit log.
>
> What makes it different from a demo is the evaluation harness: de-identification recall per identifier component, answer accuracy on gold questions, cross-patient leak count, judge tokens metered. Current numbers on 20 synthetic records: recall 1.000 whole-string and strict, accuracy 0.95, 0 leaks, extraction F1 1.00/1.00/0.99. The four post-mortems on the site are the bugs the harness caught, including the services connecting as the Postgres superuser.
>
> Apache-2.0. Runs on an M-series Mac with Ollama or on NVIDIA with the vLLM profile.

## Cross-links to add later

When the i2b2 2014 number exists: one LinkedIn post with the single number and the method,
and a top-of-post update on post 2. When the Presidio upstream PRs are open: link each from
its post and from the README.
