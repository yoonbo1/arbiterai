"""Home page for arbiterai.tech, and the trace card the How-it-works page reuses."""
from build import ONE_LINER

CHECK = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'

# One ingest job and one query job for synthetic record P00001 (the scanned variant), as the
# eval harness recorded them. Every number is from platform/docs/DATA_AND_PIPELINE.md, which
# walks this exact document through each stage with the real output; the third column is
# the module that ran the step.
INGEST_TRACE = [
    ("Document received", "tenant resolved from the API key, job queued on Redis Streams", "gateway/main.py"),
    ("Text extracted", "route: ocr (no text layer), Tesseract", "worker/extract.py"),
    ("PHI removed", "9 placeholders, map encrypted per tenant", "worker/deid.py"),
    ("Clinical facts extracted", "12 facts, 39 ms", "worker/annotate.py"),
    ("Chunk embedded", "384-dim, chunk 128", "worker/store.py"),
    ("Audit written", "job.ingest.completed · wall time 2.1 s", "audit_log"),
]
QUERY_TRACE = [
    ("Question de-identified", "same recognizers as the document", "worker/deid.py"),
    ("Retrieval scoped", "to (tenant, patient), vector + BM25", "worker/retrieval.py"),
    ("Answer drafted", "local 7B model, citation [128]", "worker/llm.py"),
    ("Validation ok", "cites_chunks true · faithfulness 1.0 · phi_leak false", "worker/graph.py"),
    ("Re-identified", "for the caller only, only the tokens the answer uses", "worker/reid.py"),
    ("Audit written", "job.query.completed · 3.6 s median", "audit_log"),
]


def _items(steps, cls):
    return "".join(
        f'<li{cls}><span class="mark">{CHECK}</span><div><div class="step-name">{n}</div>'
        f'<div class="step-desc">{d}</div></div><span class="step-meta">{m}</span></li>'
        for n, d, m in steps)


def ledger(animate=True):
    """The trace card. Animated on the home page (main.js checks the rows off in sequence);
    static, every row done, where it is reused."""
    cls = "" if animate else ' class="done"'
    return (f'<div class="ledger"{" data-animate" if animate else ""} '
            'aria-label="A real trace from the eval harness, synthetic record P00001">'
            '<div class="ledger-title"><strong>A real trace from the eval harness</strong>'
            '<span>synthetic record P00001</span></div>'
            '<div class="ledger-group"><span>Ingest</span><span>1 scanned page</span></div>'
            f'<ol>{_items(INGEST_TRACE, cls)}</ol>'
            '<div class="ledger-group"><span>Query</span><span>most recent HbA1c?</span></div>'
            f'<ol>{_items(QUERY_TRACE, cls)}</ol>'
            '<div class="ledger-foot"><span>tenant: synthetic-test-clinic</span>'
            '<span>model: qwen2.5:7b-instruct, local</span></div></div>')


HOME = f"""
<section class="hero">
  <div class="wrap hero-grid">
    <div>
      <p class="kicker">Open reference implementation</p>
      <h1>Clinical document AI you can audit.</h1>
      <p class="lede">{ONE_LINER}</p>
      <div class="actions">
        <a class="btn btn-primary btn-lg" href="/how-it-works.html">Read the architecture</a>
        <a class="btn btn-ghost btn-lg" href="/docs.html#evals">See the evals</a>
      </div>
      <p class="hero-note">Built and maintained by one engineer. Every number on this page comes from <code>eval/run_eval.py</code> or <code>eval/run_extraction_eval.py</code>, run on synthetic records. Nothing here has touched real PHI.</p>
    </div>
    {ledger()}
  </div>
</section>

<section class="on-white section-tight">
  <div class="wrap">
    <div class="section-head">
      <p class="kicker">Four properties</p>
      <h2>Each one is enforced in code and checked by a test or an eval metric.</h2>
      <p class="lede">The repository is not public yet, so these are paths rather than links. The names are exact.</p>
    </div>
    <div class="props">
      <div class="prop">
        <h3>Zero PHI reaches a model unmasked</h3>
        <p>Every node that calls a model or writes to the index asserts that the state has been de-identified first. Presidio produces the placeholders, with recognizers I had to add for labelled record numbers, phone numbers with extensions, clinician names after a title, and street addresses.</p>
        <dl>
          <dt>Enforced by</dt><dd>the <code>deidentified</code> assertions in <code>worker/graph.py</code> (annotate, chunk_embed, generate nodes) and Presidio in <code>worker/deid.py</code></dd>
          <dt>Tested by</dt><dd><code>tests/test_deid.py</code> and the de-id recall eval in <code>eval/run_eval.py</code></dd>
        </dl>
      </div>
      <div class="prop">
        <h3>Per-patient retrieval boundary, enforced in the database</h3>
        <p>The tenant comes from the API key, never from the request. Row-level security filters every PHI table on it, and retrieval adds a hard patient filter on top, so isolation does not depend on application code being bug-free.</p>
        <dl>
          <dt>Enforced by</dt><dd>the <code>tenant_isolation</code> row-level-security policies in <code>db/init.sql</code> plus the <code>WHERE tenant_id=… AND patient_id=…</code> filter in <code>worker/retrieval.py</code></dd>
          <dt>Tested by</dt><dd><code>tests/test_retrieval.py::test_query_is_hard_filtered_by_tenant_and_patient</code> and the cross-tenant probes (<code>cross_patient_leaks</code> in the eval, 0 in every run)</dd>
        </dl>
      </div>
      <div class="prop">
        <h3>Every answer carries citations to the source page</h3>
        <p>An answer must cite a retrieved chunk by id, a judge must score it at or above 0.7 against those chunks, and a second de-identification pass must find nothing. Fail any of the three and no answer is returned.</p>
        <dl>
          <dt>Enforced by</dt><dd>the validation node in <code>worker/graph.py</code> (<code>cites_chunks</code>, <code>grounded</code>, <code>phi_leak</code>) and the judge in <code>worker/llm.py</code></dd>
          <dt>Tested by</dt><dd>the eval's <code>queries_failed_validation</code>; the judge prompt measured on qwen2.5:7b at 1.0 for a supported answer and 0.0 for an unsupported one</dd>
        </dl>
      </div>
      <div class="prop">
        <h3>Append-only audit log</h3>
        <p>Every ingest, query and fact read writes an <code>audit_log</code> row with the credential, the action and the patient. The application role can insert rows and read them, and nothing else, so there is no code path that could edit history.</p>
        <dl>
          <dt>Enforced by</dt><dd><code>REVOKE UPDATE, DELETE ON audit_log FROM app_rw</code> in <code>db/init.sql</code></dd>
          <dt>Tested by</dt><dd>UPDATE and DELETE on <code>audit_log</code> as <code>app_rw</code> return permission denied</dd>
        </dl>
      </div>
    </div>
  </div>
</section>

<section class="on-ink">
  <div class="wrap">
    <div class="section-head">
      <p class="kicker">What it demonstrates</p>
      <h2>Six things a clinical document pipeline has to do, each covered end to end on synthetic records.</h2>
    </div>
    <div class="grid-3">
      <div class="pillar"><div class="mark-line"></div><h3>Cited answers over discharge summaries</h3><p>The corpus is one-page discharge summaries. The gold questions ask for the most recent HbA1c and the medication list, and an answer counts only if it cites the chunk it came from and clears the faithfulness judge. 38 of 40 in the last run; both misses are Tesseract misreads the model copied faithfully.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Scanned pages, routed honestly</h3><p>Half the records are rasterized, tilted and blurred, with no text layer. Those pages go to Tesseract, and when the router wants a vision model that is not configured, the job records <code>vlm_wanted_pages</code> instead of pretending the page was easy.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Structured facts with assertion</h3><p>Problems, medications with dose and frequency, labs, vitals and allergies, extracted by rules, Med7, bc5cdr and medspacy ConText. "Denies pneumonia" is stored as absent and a family-history line as family, so a problem list never lists what the patient does not have.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Evidence with a page citation</h3><p>Every fact links to the chunk with the largest span overlap, and <code>GET /v1/patients/{{external_id}}/facts</code> returns each one with its chunk and page. That is the primitive an evidence packet or a chart-review tool is built from.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Isolation you can probe</h3><p>The dev database holds two tenants; the second exists only to prove the first cannot see it. Key B gets 404 on tenant A's job, an <code>app_rw</code> session set to A sees zero of B's rows, and a cross-tenant INSERT violates the policy.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Two endpoints and a job poll</h3><p><code>POST /v1/documents</code>, <code>POST /v1/queries</code>, <code>GET /v1/jobs/{{id}}</code>. Idempotency keys make retries safe, and every job records its tokens and cost by model tier, judge calls included.</p></div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <p class="kicker">Benchmarks</p>
      <h2>The numbers, with the dataset named on every row.</h2>
      <p class="lede">Everything below is measured on synthetic records generated by <code>scripts/make_synthetic_docs.py</code>. The i2b2 row is the one that matters, and it stays empty until I hold credentialed access.</p>
    </div>
    <div class="tbl-wrap"><table class="bench">
      <thead><tr><th>Metric</th><th>Dataset</th><th>Value</th><th>Notes</th></tr></thead>
      <tbody>
        <tr><td>De-identification recall, whole string</td><td><span class="badge gold">Synthetic</span> 20 records</td><td class="mono">0.967 → 1.000</td><td>four iterations in a day</td></tr>
        <tr><td>De-identification recall, strict per component</td><td><span class="badge gold">Synthetic</span> 20 records</td><td class="mono">≈0.81 → 1.000</td><td>the metric that exposed surviving ZIP codes</td></tr>
        <tr><td>ZIP codes surviving de-identification</td><td><span class="badge gold">Synthetic</span> 20 records</td><td class="mono">14/20 → 0/20</td><td></td></tr>
        <tr><td>Answer accuracy, strict</td><td><span class="badge gold">Synthetic</span> 40 gold questions</td><td class="mono">0.575 → 0.95</td><td></td></tr>
        <tr><td>Cross-patient leaks</td><td><span class="badge gold">Synthetic</span> every run</td><td class="mono">0</td><td></td></tr>
        <tr><td>Clinical extraction F1: problems (assertion required) / medications (name, dose, frequency) / labs</td><td><span class="badge gold">Synthetic</span> 20 records</td><td class="mono">1.00 / 1.00 / 0.99</td><td></td></tr>
        <tr><td>De-identification recall</td><td>i2b2 2014 test set (real, credentialed)</td><td class="mono">not yet run</td><td>the number that matters; pending credentialed access</td></tr>
      </tbody>
    </table></div>
    <p class="small" style="margin-top:16px">On the regenerated corpus that includes OCR'd scans, whole-string recall is 0.992: one medical record number survived because Tesseract read its 'MRN:' label as 'MAN:'. That gap is open and tracked.</p>
    <p class="small">Before → after spans the four eval iterations of 2026-09-03; the repository's changelog records every run. <a href="/docs.html#evals">How to reproduce them</a>.</p>
  </div>
</section>

<section class="on-white">
  <div class="wrap">
    <div class="section-head">
      <p class="kicker">Failure modes I found</p>
      <h2>Bugs the eval harness caught, written up with the numbers.</h2>
      <p class="lede">Each post leads with the bug and the number, then the fix, then what to check next time.</p>
    </div>
    <div class="fm-grid">
      <article class="fm-card">
        <h3><a href="/blog/spacy-redacted-daily.html">spaCy redacted the word 'daily' — and broke 11 of 12 medication lists</a></h3>
        <p>Presidio's default date recognizer took dosing frequencies for dates, so <code>sertraline 50 mg &lt;DATE_TIME_2&gt;</code> went into the index. The fix keeps a date hit only if it contains something calendar-like.</p>
        <a class="more" href="/blog/spacy-redacted-daily.html">Read the post-mortem →</a>
      </article>
      <article class="fm-card">
        <h3><a href="/blog/deid-recall-flattering-metric.html">Our de-id recall read 0.967 while ZIP codes survived in 14 of 20 documents</a></h3>
        <p>The whole-string metric checked the full address and never noticed that only the city had been tokenized. A strict per-component metric did, on the first run.</p>
        <a class="more" href="/blog/deid-recall-flattering-metric.html">Read the post-mortem →</a>
      </article>
      <article class="fm-card">
        <h3><a href="/blog/7b-judge-citation-placement.html">The 7B judge scored identical facts 0.0 or 1.0 depending on where the citation sat</a></h3>
        <p>The faithfulness judge rejected correct answers over citation placement, escalated at 8× the cost, and its calls were half of all model traffic and unmetered.</p>
        <a class="more" href="/blog/7b-judge-citation-placement.html">Read the post-mortem →</a>
      </article>
      <article class="fm-card">
        <h3><a href="/blog/postgres-superuser-bypasses-rls.html">The services were connecting as the Postgres superuser, which silently bypasses RLS</a></h3>
        <p>Every row-level-security policy in the schema was inert, so the isolation the README described did not exist. Fixed with a plain <code>app_rw</code> role, then proven with cross-tenant probes.</p>
        <a class="more" href="/blog/postgres-superuser-bypasses-rls.html">Read the post-mortem →</a>
      </article>
    </div>
  </div>
</section>

<section class="section-tight">
  <div class="wrap author">
    <p class="kicker">Author</p>
    <p class="author-name">Yoonbo Cho</p>
    <p>I built Arbiter to have a public, checkable answer to what a correct clinical document pipeline looks like.</p>
    <p class="author-links"><a href="mailto:hello@arbiterai.tech">hello@arbiterai.tech</a><a href="https://github.com/yoonbo1" rel="me">github.com/yoonbo1</a></p>
  </div>
</section>
"""
