"""The How-it-works (architecture) page and the Security-model page. The module keeps its
old name so the import in pages.py and the file map in README.md stay simple."""
from build import gh, src
from pages_home import ledger

HOW_IT_WORKS = f"""
<section class="hero" style="padding-bottom:56px">
  <div class="wrap hero-grid">
    <div>
      <p class="kicker">How it works</p>
      <h1>From a scanned page to a cited answer, with a gate at every step.</h1>
      <p class="lede">One pipeline, two graphs. Ingest turns a document into de-identified chunks and structured facts; query turns a question into a cited, validated, re-identified answer. Every stage below names the module it lives in and the test or eval metric that covers it.</p>
    </div>
    {ledger(animate=False)}
  </div>
</section>

<section class="on-white">
  <div class="wrap">
    <div class="section-head"><p class="kicker">Pipeline</p><h2>Ten stages, in the order they run.</h2>
      <p class="lede">Ingest is stages 1 to 4 and 10. A query runs 5 to 10. The <code>deidentified</code> flag set in stage 2 is asserted by every later stage that touches a model or the index.</p></div>
    <ol class="steps stages">
      <li><h4>Text extraction, with native, OCR and vision routing</h4>
        <p>PyMuPDF renders each page at 200 dpi and keeps any native text layer. A page with more than 200 characters of native text is read as is. Otherwise Tesseract runs and reports its mean word confidence: at 75 or above with at least 40 words the page is routed to OCR; below that it goes to a vision model (Qwen2.5-VL, behind the <code>vlm</code> compose profile) if one is configured, or to OCR with <code>vlm_wanted</code> flagged so the usage stats stay honest. <code>storage_uri</code> is client input, so it is confined to <code>DATA_ROOT</code> after symlink resolution.</p>
        <p class="stage-meta"><b>Lives in</b> {src("worker/extract.py")} · <b>Covered by</b> the scanned half of the synthetic corpus in {gh("Makefile", "make eval")}; every residual miss in the changelog traces back to a Tesseract misread on one of those pages</p></li>
      <li><h4>Presidio de-identification, with a reversible per-tenant PHI map</h4>
        <p>Presidio with spaCy <code>en_core_web_lg</code>, plus recognizers Presidio does not ship: labelled MRNs, NANP phone numbers with extensions, clinician names anchored on a title, labelled address lines and bare <code>City, ST 12345</code>, and a date filter that keeps dosing frequencies such as "daily". Pages are scrubbed with shared token state, so one person gets one placeholder across a document. Overlapping candidates merge into their union, so a fragment of any above-threshold span never survives. The placeholder-to-value map goes to <code>phi_tokens</code> through <code>pgp_sym_encrypt</code> under a per-tenant key; decrypting it with another tenant's key returns "Wrong key or corrupt data".</p>
        <p class="stage-meta"><b>Lives in</b> {src("worker/deid.py")}, map storage in {src("worker/store.py")} · <b>Covered by</b> {src("tests/test_deid.py")} (real Presidio); <code>deid_recall</code> and <code>deid_recall_strict</code> in {src("eval/run_eval.py")}</p></li>
      <li><h4>Clinical fact extraction</h4>
        <p>Three layers over the de-identified text, cheapest first: regex rules for labs, vitals, allergies, medication lines, diagnosis lists, family history and follow-up; Med7 (medications with dose, route and frequency) and bc5cdr (problems) merged by character offset; medspacy sections and ConText assertion, so "Denies pneumonia" is stored as absent and a family-history line as family. Every fact links to the chunk with the largest span overlap. Median 36 ms per page inside the container.</p>
        <p class="stage-meta"><b>Lives in</b> {src("worker/annotate.py")} · <b>Covered by</b> {src("tests/test_annotate.py")}; {src("eval/run_extraction_eval.py")} ({gh("Makefile", "make eval-extraction")}), precision, recall and F1 per fact kind with assertion required for problems</p></li>
      <li><h4>Index</h4>
        <p>Chunks of up to 800 characters with 120 of overlap, split at headings and blank lines first so a medication list stays whole. Each chunk is embedded by the local embeddings service (bge-small-en-v1.5, 384 dimensions; fastembed on Apple Silicon, TEI on x86) and stored in <code>chunks</code> (pgvector, HNSW, cosine) with its page, extraction route and character offsets, under the same row-level security as every other PHI table. Only de-identified text is ever embedded.</p>
        <p class="stage-meta"><b>Lives in</b> {src("worker/store.py")} · <b>Covered by</b> the <code>deidentified</code> assertion in the <code>chunk_embed</code> node; the vector-literal and 384-dimension guards in {src("tests/test_retrieval.py")}; <code>deid_recall_strict</code>, which scans every stored chunk for every injected identifier</p></li>
      <li><h4>Retrieval scoped to (tenant, patient)</h4>
        <p>The question is de-identified with the same recognizers, embedded, and matched against this tenant's and this patient's chunks only: <code>WHERE tenant_id=%s AND patient_id=%s</code>, on top of row-level security. The top 30 by cosine form a pool; BM25 over the pool catches exact terms such as drug names; reciprocal rank fusion (k=60) merges the two rankings and the top 6 go to the model. Placeholders from different documents are renumbered into one namespace per query, so the same label cannot mean two people inside one prompt.</p>
        <p class="stage-meta"><b>Lives in</b> {src("worker/retrieval.py")}, namespace in {src("worker/reid.py")} · <b>Covered by</b> {src("tests/test_retrieval.py::test_query_is_hard_filtered_by_tenant_and_patient")} and thirteen more; <code>cross_patient_leaks</code> in the eval, 0 in every run</p></li>
      <li><h4>Answer</h4>
        <p>The small tier (<code>qwen2.5:7b-instruct</code> through Ollama here; Qwen2.5-7B-Instruct-AWQ on vLLM with a GPU) drafts an answer from the retrieved chunks and must cite each one it uses as <code>[chunk id]</code>. No cloud endpoint is called at any stage.</p>
        <p class="stage-meta"><b>Lives in</b> {src("worker/llm.py")} · <b>Covered by</b> <code>answer_accuracy</code> (strict: the first gold item verbatim) and <code>answer_accuracy_lenient</code> (drug and dose, or the lab value, for every gold item)</p></li>
      <li><h4>Validation</h4>
        <p>Three checks on every draft. <code>cites_chunks</code>: at least one retrieved chunk id appears in the answer. <code>grounded</code>: a faithfulness judge scores the answer against the chunks and must reach 0.7. <code>phi_leak</code>: a second de-identification pass over the answer, with citation markers stripped first so <code>[12]</code> is never mistaken for an identifier. <code>ok</code> is all three. The judge's tokens are metered like any other call.</p>
        <p class="stage-meta"><b>Lives in</b> the <code>validate</code> node of {src("worker/graph.py")}, judge in {src("worker/llm.py")} · <b>Covered by</b> <code>queries_failed_validation</code> in the eval; the judge prompt measured on qwen2.5:7b at 1.0 for a supported answer and 0.0 for an unsupported one</p></li>
      <li><h4>Single escalation</h4>
        <p>A draft that fails validation is regenerated once on the large tier. A PHI leak is never retried, and a second failure returns no answer rather than an unverified one. In the last eval run that was one escalation and one rejection in forty questions.</p>
        <p class="stage-meta"><b>Lives in</b> <code>after_validate</code> in {src("worker/graph.py")} · <b>Covered by</b> <code>queries_escalated</code> and <code>queries_failed_validation</code></p></li>
      <li><h4>Re-identification, for the authorized caller only</h4>
        <p>After validation passes, only the tokens the answer uses are restored: question tokens from the in-memory map, document tokens decrypted from <code>phi_tokens</code> under the tenant key, using the per-query namespace index to find which document each came from. Nothing is decrypted before the model has answered, and nothing the answer does not use. Logs, checkpoints and metrics keep the tokenized form.</p>
        <p class="stage-meta"><b>Lives in</b> {src("worker/reid.py")} · <b>Covered by</b> {src("tests/test_reid.py")}, including the case where a question about one clinician could name another</p></li>
      <li><h4>Audit write</h4>
        <p>Every job ends with an <code>audit_log</code> row: <code>job.ingest.completed</code> with pages, routes and fact counts; <code>job.query.completed</code> with the validation summary and whether anything was re-identified; <code>facts.read</code> on the facts endpoint. The application role holds INSERT and SELECT on the table and nothing else.</p>
        <p class="stage-meta"><b>Lives in</b> {src("db/init.sql")}, writes in {src("worker/store.py")} and {src("gateway/main.py")} · <b>Covered by</b> <code>REVOKE UPDATE, DELETE ON audit_log FROM app_rw</code>; UPDATE and DELETE as <code>app_rw</code> return permission denied</p></li>
    </ol>
  </div>
</section>

<section>
  <div class="wrap grid-2">
    <div>
      <p class="kicker">Why an arbiter</p>
      <h2>The model is not in charge.</h2>
      <p>Language models are persuasive, and a clinical record is the wrong place to be persuaded. So there is a gate on each side of the model: de-identification between the document and the model, and validation between the model and the caller. Cite the source, clear the faithfulness threshold, leak nothing, or return no answer. The arbiter is the part that says no, and the eval harness is what shows it saying no for the right reasons.</p>
    </div>
    <div>
      <p class="kicker">Engineering note</p>
      <h2>Cost that scales with difficulty, not volume.</h2>
      <p>Native text is free: PyMuPDF reads the layer. Tesseract costs about 1.5 to 2 seconds per page on the Apple Silicon dev machine; the scanned-page ingest in the trace above is 2.1 s wall, annotation included. A vision model runs only when OCR confidence is under 75 or the page has fewer than 40 words, which means forms, tables and handwriting, not clean scans. On the answer side the 7B model goes first and the large tier runs at most once, after a validation failure: one escalation in forty questions in the last run. The routing is what lets the expensive checks run on every request.</p>
    </div>
  </div>
</section>

<section class="on-ink">
  <div class="wrap">
    <div class="section-head"><p class="kicker">Interface</p><h2>Two endpoints and a job poll. Asynchronous by design.</h2>
      <p class="lede">Requests return a job id immediately and never block on model inference. The worker reads a Redis stream with at-least-once delivery, and ingest is idempotent so a redelivered message cannot double-process.</p></div>
    <div class="grid-2">
      <div>
<pre><code>POST /v1/documents
Authorization: Bearer hipaa_live_…
Idempotency-Key: ingest-P00001-scan

{{ "patient_external_id": "P00001",
  "doc_type": "discharge_summary",
  "storage_uri": "/data/synthetic/scan/P00001.pdf" }}

→ 202 {{ "job_id": "f9fc0185-…" }}</code></pre>
      </div>
      <div>
<pre><code>POST /v1/queries
Authorization: Bearer hipaa_live_…

{{ "patient_external_id": "P00001",
  "question": "What is the most recent HbA1c?" }}

→ 202 {{ "job_id": "…" }}

GET /v1/jobs/…
→ {{ "status": "done",
    "result": {{ "answer": "The most recent HbA1c is 5.7% [128].",
                "citations": [128],
                "validation": {{ "ok": true, "cites_chunks": true,
                                "faithfulness": 1.0, "grounded": true,
                                "phi_leak": false }} }} }}</code></pre>
      </div>
    </div>
    <p class="small">Any HTTP client works. The full endpoint table, including <code>GET /v1/patients/{{external_id}}/facts</code>, is in the <a href="/docs.html#api" style="color:#fff">docs</a>.</p>
  </div>
</section>

<section class="on-white section-tight">
  <div class="wrap grid-2">
    <div>
      <p class="kicker">Observability</p>
      <h2>Every job records what it cost.</h2>
    </div>
    <div>
      <p>The <code>jobs</code> row for each ingest and query carries <code>tokens_small</code>, <code>tokens_large</code> and <code>cost_cents</code> at placeholder rates, judge calls included. That is how the eval reports tokens and cost per query, and how the judge's calls turned out to be half of all model traffic when they were still unmetered. The audit row beside it carries the extraction route mix per document, so the OCR and vision share of a corpus comes from one table.</p>
    </div>
  </div>
</section>

<section class="cta-band section-tight">
  <div class="wrap"><h2>Run it on your own machine.</h2>
    <div class="actions"><a class="btn btn-primary btn-lg" href="/docs.html">Run it locally</a><a class="btn btn-ghost btn-lg" href="/security.html">Read the security model</a></div></div>
</section>
"""

SECURITY = f"""
<section class="hero" style="padding-bottom:48px">
  <div class="wrap">
    <p class="kicker">Security model</p>
    <h1 style="max-width:18ch">Five invariants, each enforced in code and checked by a test.</h1>
    <p class="lede">This is a design-and-verification document, not a compliance page. For each property: what the code does to make it hold, and what would fail if it stopped holding.</p>
  </div>
</section>

<section class="on-white">
  <div class="wrap">
    <div class="section-head"><h2>Invariants</h2></div>
    <ol class="steps stages">
      <li><h4>Nothing reaches a model until the state is de-identified</h4>
        <p>The ingest and query graphs carry a <code>deidentified</code> flag that only the de-identification node sets. The annotate, chunk_embed and generate nodes assert it before doing anything, so a refactor that reorders the graph fails loudly instead of leaking quietly. The LangGraph checkpointer is off by default because the state before that node holds the raw text and the plaintext map.</p>
        <p class="stage-meta"><b>Enforced</b> by <code>assert state["deidentified"]</code> in {src("worker/graph.py")} (annotate, chunk_embed, generate); Presidio and the added recognizers in {src("worker/deid.py")}; <code>CHECKPOINTER=none</code><br><b>Tested</b> by {src("tests/test_deid.py")} (real Presidio, thirty-plus cases: labelled MRNs, phones with extensions, address lines, titles, frequencies kept, calendar dates removed, round trip through <code>restore</code>); <code>deid_recall</code> and <code>deid_recall_strict</code> in {src("eval/run_eval.py")}</p></li>
      <li><h4>The PHI map never enters the vector store</h4>
        <p>Chunks hold placeholder text and an embedding of placeholder text. The map from placeholder to value goes to a separate table, <code>phi_tokens</code>, encrypted inside Postgres with <code>pgp_sym_encrypt</code> under a per-tenant key. Decrypting with another tenant's key returns "Wrong key or corrupt data". Only the re-identification step calls <code>pgp_sym_decrypt</code>, and only for the tokens the answer uses.</p>
        <p class="stage-meta"><b>Enforced</b> in {src("worker/store.py")} (chunks are written from the de-identified text; the map only ever through <code>pgp_sym_encrypt</code>) and {src("worker/reid.py")}<br><b>Tested</b> by <code>deid_recall_strict</code>, which scans every stored chunk for every component of every injected identifier (1.000 on the 20-record set); {src("tests/test_reid.py::test_restore_uses_the_right_document_and_only_needed_tokens")}</p></li>
      <li><h4>Retrieval is hard-filtered on patient</h4>
        <p>Every retrieval query carries <code>WHERE tenant_id=%s AND patient_id=%s</code> in its SQL, on top of the row-level-security policy on <code>chunks</code>. The patient is resolved inside the tenant, so an external id that belongs to another tenant resolves to nothing, and a question about a patient with nothing indexed takes the <code>no_chunks</code> branch without a model call.</p>
        <p class="stage-meta"><b>Enforced</b> in {src("worker/retrieval.py::hybrid")}; the <code>tenant_isolation</code> policy on every PHI table in {src("db/init.sql")}<br><b>Tested</b> by {src("tests/test_retrieval.py::test_query_is_hard_filtered_by_tenant_and_patient")}, which checks the SQL and the bind parameters; <code>cross_patient_leaks</code> in {src("eval/run_eval.py")}, which checks every answer for every other patient's injected identifiers, 0 in every run</p></li>
      <li><h4>Tenant identity comes from the credential, never a client-supplied field</h4>
        <p>An API key is stored as an HMAC-SHA256 under a pepper kept outside the database, and the lookup returns the tenant. Request bodies have no tenant field to send. Every transaction runs <code>set_config('app.tenant_id', …, true)</code>, and the application connects as <code>app_rw</code>, a plain role the row-level-security policies apply to. Key lookups are cached for 60 seconds, so revocation lands within a minute.</p>
        <p class="stage-meta"><b>Enforced</b> in {src("gateway/auth.py")}; per-transaction <code>app.tenant_id</code> in {src("gateway/main.py")} and {src("worker/store.py")}; <code>app_rw</code> with its password set by {src("db/02_app_role.sh")}<br><b>Tested</b> by {src("tests/test_auth.py")} (hashing, pepper rotation, revoked and tampered keys, rate limits); the cross-tenant probes below; {src("eval/run_eval.py")} refuses to run as a superuser or a BYPASSRLS role, so its leak count cannot be flattered by the same mistake twice</p></li>
      <li><h4>The audit log is append-only</h4>
        <p>Every ingest, query and fact read writes an <code>audit_log</code> row with the credential, the action, the patient and a detail object. The application role holds INSERT and SELECT on that table and nothing else, so there is no code path that could edit history.</p>
        <p class="stage-meta"><b>Enforced</b> by <code>REVOKE UPDATE, DELETE ON audit_log FROM app_rw</code> in {src("db/init.sql")} (the blanket grant above it had included UPDATE; that was the bug)<br><b>Tested</b> by running UPDATE and DELETE on <code>audit_log</code> as <code>app_rw</code>: permission denied</p></li>
    </ol>
  </div>
</section>

<section>
  <div class="wrap prose">
    <h2 id="superuser">The superuser finding</h2>
    <p>The gateway and the worker originally connected to Postgres as the database owner, a superuser. Row-level security does not apply to a superuser, so every policy in the schema was inert. The README said other tenants' jobs return 404 via RLS, and that was false: the isolation the code described did not exist. It surfaced during the first end-to-end bring-up, not in the unit tests, which fake the pool.</p>
    <p>The fix is small. The application connects as <code>app_rw</code>, a plain login role the policies apply to. Its password comes from the environment through {src("db/02_app_role.sh")}, because Postgres runs init <code>.sql</code> files without environment substitution and <code>.sh</code> files with it, which also removed the hard-coded password from {src("db/init.sql", "init.sql")}. The role gets DELETE on <code>chunks</code> and <code>phi_tokens</code>, which re-ingest needs, and loses UPDATE and DELETE on <code>audit_log</code>.</p>
    <p>Then the probes, run against the live stack and kept: key B gets 404 on tenant A's job; an <code>app_rw</code> session with <code>app.tenant_id</code> set to A sees zero of B's rows; a cross-tenant INSERT while set to A violates the policy. And {src("eval/run_eval.py")} now refuses to run as a superuser or a BYPASSRLS role.</p>
    <p>What I took from it: isolation should not depend on application code being bug-free, and it also should not depend on a connection string being right. The probes are what make the second half true.</p>
  </div>
</section>

<section class="section-tight">
  <div class="wrap">
    <div class="callout"><p>This is a reference implementation maintained by one engineer. It is not a hosted service, does not process real PHI, and no Business Associate Agreement is offered. If you want to run it against real records, run it in your own environment under your own compliance program.</p></div>
  </div>
</section>

<section class="on-white">
  <div class="wrap grid-2">
    <div>
      <h2>Also in the code</h2>
      <ul>
        <li>Scoped credentials: <code>ingest</code>, <code>query</code>, <code>admin</code>. A key without the scope gets 403.</li>
        <li>Models are local: Ollama on Apple Silicon or vLLM on NVIDIA. No cloud model endpoint is configured anywhere, and cloud tracing is off (<code>LANGCHAIN_TRACING_V2=false</code>).</li>
        <li>medspacy's sentence splitter logs document text at debug level by default; that logging is disabled at import, so de-identified text never reaches container logs.</li>
        <li><code>storage_uri</code> is confined to <code>DATA_ROOT</code> after symlink resolution; a <code>/etc/passwd</code> probe fails the job cleanly.</li>
        <li>Idempotent jobs: a retried POST with the same <code>Idempotency-Key</code> maps to the same job.</li>
      </ul>
    </div>
    <div>
      <h2>Not in the reference implementation</h2>
      <ul>
        <li>TLS between the internal services. The public site has it; the compose stack does not.</li>
        <li>A KMS-issued key per tenant. Today the map key is derived from <code>TENANT_KEK</code> and the tenant id.</li>
        <li>A written risk analysis, workforce training, incident response: the things a compliance program adds around the software, which the software cannot supply.</li>
        <li>Real data, ever. {gh("TODO.md")} in the repository lists what would have to be true first.</li>
      </ul>
    </div>
  </div>
</section>
"""
