"""Page registry for arbiterai.tech, plus the docs, about, contact, legal and 404 bodies.
Each PAGES entry: (path, <title>, meta description, body HTML[, meta dict])."""
from build import ONE_LINER, SHORT
from pages_home import HOME
from pages_product import HOW_IT_WORKS, SECURITY
from pages_blog import BLOG_PAGES

DOCS = """
<section class="hero" style="padding-bottom:40px">
  <div class="wrap">
    <p class="kicker">Documentation</p>
    <h1 style="max-width:16ch">Run it, then run the evals.</h1>
    <p class="lede">Everything here runs on one machine with no cloud API. The records are synthetic, and the numbers on the home page are what these commands produce.</p>
  </div>
</section>

<section class="on-white">
  <div class="wrap prose">
    <h2 id="run">Run it locally</h2>
    <h3>Prerequisites</h3>
    <ul>
      <li>Docker (validated with Colima on Apple Silicon).</li>
      <li>Python 3.12. <code>make venv</code> creates <code>.venv/</code>; 3.14 is too new for spaCy and Presidio.</li>
      <li>A local model. On Apple Silicon: Ollama with <code>qwen2.5:7b-instruct</code> (<code>brew install ollama</code>, <code>ollama pull qwen2.5:7b-instruct</code>, then <code>make llm</code> in a second terminal). On NVIDIA: the vLLM <code>gpu</code> compose profile, and <code>vlm</code> for the vision model on a second GPU. Without a vision model, low-confidence scans fall back to OCR and the job records that one was wanted.</li>
    </ul>
    <h3>Bring the stack up</h3>
<pre><code>cp platform/.env.example platform/.env   # then set every change-me (openssl rand -hex 24)
make up              # postgres (pgvector), redis, embeddings, gateway, worker
make synth N=20      # 20 synthetic records with injected fake identifiers -> platform/data/synthetic/
make bootstrap       # dev tenant + one API key -> platform/.env.dev-tenant (git-ignored)</code></pre>
    <p><code>make bootstrap</code> prints the tenant id and the key once. The gateway listens on <code>127.0.0.1:8080</code>.</p>
    <h3>Ingest a document</h3>
<pre><code>curl -X POST http://127.0.0.1:8080/v1/documents \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Idempotency-Key: ingest-P00001-scan" \\
  -H "Content-Type: application/json" \\
  -d '{"patient_external_id":"P00001","doc_type":"discharge_summary",
       "storage_uri":"/data/synthetic/scan/P00001.pdf"}'

→ 202 {"job_id":"f9fc0185-…"}</code></pre>
    <p>Odd-numbered records are the scanned variants under <code>scan/</code>; the rest have a text layer under <code>clean/</code>. <code>/data</code> is the worker's mount of <code>platform/data/</code>.</p>
    <h3>Ask a question</h3>
<pre><code>curl -X POST http://127.0.0.1:8080/v1/queries \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"patient_external_id":"P00001","question":"What is the most recent HbA1c?"}'

→ 202 {"job_id":"…"}</code></pre>
    <h3>Read the result</h3>
<pre><code>curl http://127.0.0.1:8080/v1/jobs/$JOB_ID -H "Authorization: Bearer $API_KEY"

{"job_id":"…","status":"done",
 "result":{"answer":"The most recent HbA1c is 5.7% [128].",
           "citations":[128],
           "validation":{"ok":true,"cites_chunks":true,"faithfulness":1.0,
                         "grounded":true,"phi_leak":false,"attempts":1,
                         "tokens_restored":0},
           "errors":[]},
 "finished_at":"…"}</code></pre>
    <p>Citation numbers are chunk ids. Each chunk carries its page and character offsets, so a reviewer can open the source at the right place. The answer is re-identified for the caller; everything stored stays de-identified. A rejected answer comes back as <code>status: failed</code> with the <code>validation</code> object that explains why, never as an unverified answer.</p>

    <h2 id="evals">Run the evals</h2>
<pre><code>make eval LIMIT=20              # eval/run_eval.py: ingest, de-id recall, 40 gold questions, leaks, latency, cost
make eval-extraction LIMIT=20   # eval/run_extraction_eval.py: clinical facts against the manifest's gold_facts
make test                       # pytest, no Docker needed: 130 passed, 2 skipped, 2 xfailed</code></pre>
    <p>Both evals read <code>TENANT_ID</code>, <code>API_KEY</code>, <code>DATABASE_URL</code> and <code>GATEWAY</code> from <code>platform/.env.dev-tenant</code>, written by <code>make bootstrap</code>. <code>run_eval.py</code> refuses to run as a superuser or a BYPASSRLS role, because a leak check that bypasses row-level security measures nothing. One run of twenty records and forty questions takes under three minutes on an M4.</p>
    <h3>What each metric means</h3>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Metric</th><th>Meaning</th></tr></thead>
      <tbody>
        <tr><td><code>deid_recall</code></td><td>Whole string. For every injected identifier (name, date of birth, MRN, phone, address, physician), does the full string survive anywhere in the stored chunks? 1 minus survivors over injected.</td></tr>
        <tr><td><code>deid_recall_strict</code></td><td>Per component. The same check on every comma-separated component of every identifier, so a surviving street line or ZIP code counts as a miss even when the whole address string does not appear. This is the metric that exposed ZIP codes in 14 of 20 documents.</td></tr>
        <tr><td><code>answer_accuracy</code></td><td>Strict. The first gold item appears verbatim in the answer.</td></tr>
        <tr><td><code>answer_accuracy_lenient</code></td><td>The first two tokens of every gold item (drug and dose, or the lab value) appear in the answer.</td></tr>
        <tr><td><code>cross_patient_leaks</code></td><td>Answers for one patient that contain another patient's injected identifier. Zero in every run.</td></tr>
        <tr><td><code>queries_failed_validation</code></td><td>Answers rejected by the validation node (no citation, faithfulness under 0.7, or a PHI leak) and therefore not returned.</td></tr>
        <tr><td><code>queries_escalated</code></td><td>Questions that needed the one permitted retry on the large tier.</td></tr>
        <tr><td><code>faithfulness</code></td><td>Per query, the judge's score of the answer against the retrieved chunks; <code>grounded</code> is faithfulness at or above 0.7.</td></tr>
        <tr><td><code>p50_s</code>, <code>p95_s</code></td><td>Median and 95th-percentile query latency, submit to done.</td></tr>
        <tr><td><code>tokens_small</code>, <code>tokens_large</code>, <code>cost_cents</code>, <code>cost_cents_per_query</code></td><td>From the <code>jobs</code> table, at placeholder rates. Judge calls are metered too.</td></tr>
      </tbody>
    </table></div>
    <p>The extraction eval reports precision, recall and F1 per fact kind (problem, medication, lab, vital, allergy). Problems must match on assertion; medications on name, dose and frequency. It also reports separately how many negated or family-history conditions were wrongly stored as present.</p>
    <h3>Adding gold questions</h3>
    <p>Gold questions live in the manifest. <code>scripts/make_synthetic_docs.py</code> writes a <code>gold_qa</code> list per record (<code>{"q": …, "a": …}</code>) next to <code>injected_phi</code> and <code>gold_facts</code>. Add a question there, regenerate with <code>make synth N=20</code>, and <code>run_eval.py</code> picks it up. The first gold item is what the strict metric checks verbatim, so put the most specific value first.</p>

    <h2 id="data">Data</h2>
    <p>Every record that ships with the reference implementation is synthetic. No real patient has ever been near it. <code>scripts/make_synthetic_docs.py</code> generates one-page discharge summaries with Faker, seeded so the corpus is reproducible, and plants six identifiers per record that the de-identification eval must remove: a name, a date of birth, a medical record number, a phone number with an extension, a street address, and an attending physician. Each record also carries the gold facts: two diagnoses, three medications, an HbA1c, a blood pressure, an LDL, two negated findings, one family-history condition, and an allergy with reaction or a note of no known allergies.</p>
    <p>Half the corpus is rasterized as scans: every odd-numbered record's PDF is rendered, rotated up to 1.5 degrees, blurred, and saved as an image with no text layer, the way a fax arrives. <code>--scan-mode bilevel</code> gives 1-bit at 300 dpi for harsher fax realism. The manifest, <code>platform/data/synthetic/manifest.json</code>, is the ground truth: <code>injected_phi</code>, <code>gold_qa</code> and <code>gold_facts</code> per record.</p>
    <h3>Pointing the harness at i2b2 2014</h3>
    <p>The n2c2/i2b2 2014 de-identification corpus is the credible benchmark for this, and it needs a data use agreement. Once you hold credentialed access: render each note to a PDF (one per record, in the same layout the synthetic generator uses, or any layout Tesseract can read), and write a manifest with one entry per record whose <code>injected_phi</code> list is the gold PHI annotations for that note. <code>run_eval.py --manifest</code> then reports the same recall metrics against real annotations. The QA metrics need <code>gold_qa</code>, so give each record at least one question whose answer is a value in the note, or read only the recall fields.</p>

    <h2 id="api">API</h2>
    <p>Three endpoints for the reference implementation, plus admin routes for tenants and keys. There is no shared public API: <code>&lt;your-deployment&gt;</code> is wherever you run the gateway.</p>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Method</th><th>Path</th><th>Scope</th><th>Notes</th></tr></thead>
      <tbody>
        <tr><td>POST</td><td><code>/v1/documents</code></td><td>ingest</td><td><code>{patient_external_id, doc_type, storage_uri}</code> → 202 <code>{job_id}</code></td></tr>
        <tr><td>POST</td><td><code>/v1/queries</code></td><td>query</td><td><code>{patient_external_id, question, max_chunks}</code> → 202 <code>{job_id}</code></td></tr>
        <tr><td>GET</td><td><code>/v1/jobs/{id}</code></td><td>any</td><td>status and result; another tenant's job is a 404</td></tr>
        <tr><td>GET</td><td><code>/v1/patients/{external_id}/facts</code></td><td>query</td><td>de-identified structured facts with chunk and page; <code>?kind=</code> filters, <code>?active=</code> (default true) hides absent, family, conditional and possible assertions; audited as <code>facts.read</code></td></tr>
      </tbody>
    </table></div>
<pre><code>curl -X POST https://&lt;your-deployment&gt;/v1/documents \\
  -H "Authorization: Bearer hipaa_live_…" \\
  -H "Idempotency-Key: intake-0001" \\
  -H "Content-Type: application/json" \\
  -d '{"patient_external_id":"P00001","doc_type":"discharge_summary",
       "storage_uri":"/data/intake/P00001.pdf"}'</code></pre>
<pre><code>curl https://&lt;your-deployment&gt;/v1/patients/P00001/facts?kind=medication \\
  -H "Authorization: Bearer hipaa_live_…"

{"patient_external_id":"P00001","count":3,"active_only":true,
 "facts":[{"kind":"medication","normalized":"lisinopril",
           "attributes":{"dose":"10 mg","frequency":"daily"},
           "assertion":"present","section":"medications",
           "chunk_id":128,"page":1,"confidence":0.95,"extractor":"rules"}, …]}</code></pre>

    <h2 id="concepts">Concepts</h2>
    <h3>Tenants and patients</h3>
    <p>Your tenant is identified by your credential. Patients are identified by an <code>external_id</code> you choose, typically your own record number. Queries are always scoped to one patient.</p>
    <h3>Idempotency</h3>
    <p>Send an <code>Idempotency-Key</code> on every POST. Retrying with the same key returns the original job instead of creating a duplicate, so a network failure never double-processes.</p>
    <h3>Job states</h3>
    <p><code>queued</code>, <code>processing</code>, <code>done</code>, <code>failed</code>. A <code>failed</code> query includes a <code>validation</code> object explaining why it was rejected rather than returning an unverified answer.</p>
    <h3>Scopes and rate limits</h3>
    <p>A key carries scopes (<code>ingest</code>, <code>query</code>, <code>admin</code>) and a per-minute limit, both set when it is minted. Exceeding the limit returns <code>429</code>. Revocation takes effect within 60 seconds.</p>

    <h2 id="errors">Errors</h2>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Status</th><th>Meaning</th></tr></thead>
      <tbody>
        <tr><td>401</td><td>Missing, expired, or revoked credential, or a tenant that is not active</td></tr>
        <tr><td>403</td><td>Credential lacks the required scope</td></tr>
        <tr><td>404</td><td>Job or patient not found, including those belonging to another tenant</td></tr>
        <tr><td>422</td><td>Request body failed validation</td></tr>
        <tr><td>429</td><td>Rate limit exceeded</td></tr>
      </tbody>
    </table></div>
  </div>
</section>
"""

ABOUT = """
<section class="hero" style="padding-bottom:40px">
  <div class="wrap">
    <p class="kicker">About</p>
    <h1 style="max-width:18ch">One engineer, one question, one checkable answer.</h1>
    <p class="lede">I wanted a public, checkable answer to "what does a correct clinical document pipeline look like?" Arbiter AI is that answer, with the evaluation harness that shows where it holds and where it does not yet.</p>
  </div>
</section>

<section class="on-white">
  <div class="wrap grid-2">
    <div>
      <h2>Who built it</h2>
      <p>Yoonbo Cho. I designed, built and evaluated every part of it: the pipeline, the schema and its isolation policies, the eval harness, and the post-mortems on what the harness caught.</p>
      <p class="author-links"><a href="mailto:hello@arbiterai.tech">hello@arbiterai.tech</a><a href="https://github.com/yoonbo1" rel="me">github.com/yoonbo1</a></p>
      <h2>Why</h2>
      <p>The hard part of putting language models in front of medical records is not getting them to answer. It is getting them to answer only when they can prove it, never with information they should not have seen, and being able to show both. Most write-ups on this stop at the diagram. I wanted the code, the tests, the numbers, and the bugs.</p>
    </div>
    <div>
      <h2>What it is not</h2>
      <ul>
        <li>Not a product. There is nothing to buy and no plan to sell.</li>
        <li>Not a hosted service. It runs where you run it.</li>
        <li>Not a place for real records. Every record it ships is synthetic, and no Business Associate Agreement is offered. If you want to run it against real data, run it in your own environment under your own compliance program.</li>
        <li>Not certified. There is no HIPAA certification, and no SOC 2 or HITRUST report is claimed.</li>
      </ul>
      <p><a href="/security.html">The security model</a> says exactly what is in the code and what is not. <a href="/docs.html">The docs</a> show how to run it and reproduce the numbers.</p>
    </div>
  </div>
</section>
"""

CONTACT = """
<section class="hero" style="padding-bottom:40px">
  <div class="wrap">
    <p class="kicker">Contact</p>
    <h1 style="max-width:14ch">Get in touch.</h1>
    <p class="lede">Questions about the architecture, the evals or the post-mortems; corrections; or a dataset you think the harness should be run on.</p>
    <p class="author-links"><a href="mailto:hello@arbiterai.tech">hello@arbiterai.tech</a><a href="https://github.com/yoonbo1" rel="me">github.com/yoonbo1</a></p>
    <p class="small">Please do not send protected health information by email. Nothing here is set up to receive it.</p>
  </div>
</section>
"""

PRIVACY = """
<section class="section-tight"><div class="wrap prose">
<p class="kicker">Legal</p><h1>Privacy policy</h1>
<p class="small">Last updated: September 4, 2026.</p>
<h2>Scope</h2><p>This policy covers the website arbiterai.tech, which I, Yoonbo Cho, operate. Contact: hello@arbiterai.tech. The site describes a reference implementation; there is no hosted service and no account to create.</p>
<h2>What the site collects</h2><p>The site has no forms, sets no cookies of its own, and runs no analytics script. The host keeps standard request logs (IP address, user agent, path, time) to operate the service. If you email me, I keep the email in order to reply to it.</p>
<h2>Third parties</h2><p>Fonts are loaded from Google Fonts, which receives your IP address when the font files are fetched. Nothing else on the page calls out to another domain.</p>
<h2>Your rights</h2><p>Depending on where you live, you may have rights to access, correct, or delete personal information I hold about you. Email hello@arbiterai.tech.</p>
<h2>Changes</h2><p>Updates are posted on this page with the date above.</p>
</div></section>
"""

TERMS = """
<section class="section-tight"><div class="wrap prose">
<p class="kicker">Legal</p><h1>Terms of use</h1>
<p class="small">Last updated: September 4, 2026.</p>
<h2>Use of this website</h2><p>Content on arbiterai.tech is provided for information. You may not crawl it at a rate that affects the site, or attempt to access non-public areas of it.</p>
<h2>No medical advice</h2><p>Arbiter AI is software that retrieves and summarizes information from documents. It does not provide medical advice, diagnosis, or treatment recommendations, and any output from it must be reviewed by qualified personnel before any clinical action.</p>
<h2>The software</h2><p>The code described on this site is a reference implementation. It is not offered as a service, comes with no warranty, and processes no real protected health information. If you run it, you do so in your own environment and under your own compliance program.</p>
<h2>Intellectual property</h2><p>The Arbiter AI name, logo, and the content of this website are mine.</p>
<h2>Disclaimer and limitation</h2><p>The website is provided "as is". To the extent permitted by law, I disclaim warranties regarding the website and am not liable for indirect or consequential damages arising from its use.</p>
<h2>Questions</h2><p>Email <a href="mailto:hello@arbiterai.tech">hello@arbiterai.tech</a>.</p>
</div></section>
"""

NOTFOUND = """
<section><div class="wrap center"><h1>Page not found</h1><p class="lede">The page you asked for does not exist or has moved.</p><a class="btn btn-primary" href="/">Back to the home page</a></div></section>
"""

PAGES = [
    ("index.html", "Arbiter AI — Clinical document AI you can audit", ONE_LINER, HOME),
    ("how-it-works.html", "How it works — Arbiter AI", SHORT, HOW_IT_WORKS),
    ("security.html", "Security model — Arbiter AI", SHORT, SECURITY),
    ("docs.html", "Docs — Arbiter AI", SHORT, DOCS),
    ("about.html", "About — Arbiter AI", SHORT, ABOUT),
    # Blog index and one entry per post. Each carries a meta dict (og:type, sitemap
    # lastmod, JSON-LD) that build.py's render() folds into the shared shell.
    *BLOG_PAGES,
    ("contact.html", "Contact — Arbiter AI", SHORT, CONTACT),
    ("privacy.html", "Privacy policy — Arbiter AI", SHORT, PRIVACY),
    ("terms.html", "Terms of use — Arbiter AI", SHORT, TERMS),
    ("404.html", "Page not found — Arbiter AI", SHORT, NOTFOUND),
]
