from pages_home import ledger

PRODUCT = f"""
<section class="hero" style="padding-bottom:56px">
  <div class="wrap hero-grid">
    <div>
      <p class="kicker">Product</p>
      <h1>From a scanned page to a cited answer, with a checkpoint at every step.</h1>
      <p class="lede">Arbiter AI is a document pipeline and a question-answering service built as one system. Documents go in once. Questions can be asked for as long as the record exists.</p>
    </div>
    {ledger(animate=False)}
  </div>
</section>

<section class="on-white">
  <div class="wrap">
    <div class="section-head"><p class="kicker">Ingestion</p><h2>Reading documents the cheapest way that is still accurate.</h2></div>
    <div class="flow">
      <div><b>Receive</b><span>PDF, TIFF, JPEG, fax exports. Stored encrypted, tagged to your organization and a patient identifier you control.</span></div>
      <div><b>Route</b><span>Pages with a native text layer are read directly. Scans are assessed for OCR confidence.</span></div>
      <div><b>Extract</b><span>Clean scans go to OCR. Forms, tables, handwriting, and low-confidence pages go to a vision model that transcribes rather than summarizes.</span></div>
      <div><b>De-identify</b><span>Identifiers are detected and replaced with consistent tokens. The mapping is encrypted with your organization's key.</span></div>
      <div><b>Index</b><span>Section-aware chunks are embedded and stored with page and patient references. Only de-identified text is ever indexed.</span></div>
    </div>
    <p class="small" style="margin-top:20px">Typical mix on real clinic corpora: roughly 60% native text, 25% OCR, 15% vision. The vision share is what determines cost, and the router keeps it to the pages that need it.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head"><p class="kicker">Answering</p><h2>Retrieval that cannot wander, generation that must cite.</h2></div>
    <div class="row">
      <h3>Scoped retrieval</h3>
      <div><p>Every query carries an organization identifier derived from the API credential and a patient identifier supplied by the caller. Both are hard filters, enforced by database row-level security, not just by the application. Vector similarity and keyword search are fused so that both paraphrases and exact terms like drug names are found.</p></div>
    </div>
    <div class="row">
      <h3>Tiered generation</h3>
      <div><p>A small, fast model drafts the answer from the retrieved passages. If verification fails, the question is escalated once to a larger model. Most questions never need the escalation, which is why the service stays inexpensive at volume.</p></div>
    </div>
    <div class="row">
      <h3>Verification gate</h3>
      <div><p>Three checks run on every draft: each factual sentence must cite a retrieved passage; a grounding score confirms the passages support the claims; a second de-identification pass confirms no identifier has been reconstructed. A failed leak check is never retried.</p></div>
    </div>
    <div class="row">
      <h3>Re-identification, last</h3>
      <div><p>Tokens are swapped back to real values only in the final response, only for the authenticated requester, only for the patient they asked about. Logs, checkpoints, and metrics keep the tokenized form.</p></div>
    </div>
  </div>
</section>

<section class="on-ink">
  <div class="wrap">
    <div class="section-head"><p class="kicker">Integration</p><h2>Two endpoints. Asynchronous by design.</h2>
      <p class="lede">Requests return a job identifier immediately and never block on model inference, so bursts from a batch import or a busy clinic morning queue rather than fail.</p></div>
    <div class="grid-2">
      <div>
<pre><code>POST /v1/documents
Authorization: Bearer arb_live_…
Idempotency-Key: intake-2026-09-02-0042

{{ "patient_external_id": "MRN-48213",
  "doc_type": "discharge_summary",
  "storage_uri": "s3://your-bucket/…/dc-summary.pdf" }}

→ 202 {{ "job_id": "7f3a…c21e" }}</code></pre>
      </div>
      <div>
<pre><code>POST /v1/queries
Authorization: Bearer arb_live_…

{{ "patient_external_id": "MRN-48213",
  "question": "Which medications were discontinued at discharge and why?" }}

→ 202 {{ "job_id": "9b10…e77d" }}

GET /v1/jobs/9b10…e77d
→ {{ "status": "done",
    "result": {{ "answer": "…[14][17]", "citations": [14, 17],
                "validation": {{ "grounded": 0.94, "phi_leak": false }} }} }}</code></pre>
      </div>
    </div>
    <p class="small">SDKs are not required. Any HTTP client works. Webhooks for job completion are available on Dedicated and On-premises plans.</p>
  </div>
</section>

<section class="on-white">
  <div class="wrap">
    <div class="section-head"><p class="kicker">Operations</p><h2>What you see after go-live.</h2></div>
    <div class="grid-3">
      <div class="pillar"><div class="mark-line"></div><h3>Audit log</h3><p>Every submission, every answer, every re-identification event, with the credential and the patient reference. Exportable to your SIEM.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Cost per request</h3><p>Token usage by model tier is recorded on every job, so you can see which document types and questions drive spend.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Quality metrics</h3><p>Grounding scores, escalation rate, extraction route mix, and de-identification recall on planted test identifiers, reported monthly.</p></div>
    </div>
  </div>
</section>

<section class="cta-band section-tight">
  <div class="wrap"><h2>Walk through the pipeline on your own document types.</h2>
    <div class="actions"><a class="btn btn-primary btn-lg" href="/contact.html">Request a demo</a><a class="btn btn-ghost btn-lg" href="/docs.html">Read the docs</a></div></div>
</section>
"""

SECURITY = """
<section class="hero" style="padding-bottom:48px">
  <div class="wrap">
    <p class="kicker">Security and compliance</p>
    <h1 style="max-width:16ch">Designed so that compliance is a property of the system, not a promise in a slide.</h1>
    <p class="lede">This page describes how Arbiter AI handles protected health information, what we sign, what we have, and what we are still working toward. We would rather you know exactly where we stand.</p>
  </div>
</section>

<section class="on-white">
  <div class="wrap">
    <div class="section-head"><h2>Technical safeguards</h2></div>
    <div class="grid-3">
      <div class="pillar"><div class="mark-line"></div><h3>Encryption</h3><p>TLS 1.2+ in transit, including between internal services. AES-256 at rest for storage volumes and object storage. The PHI token map is additionally encrypted with a per-organization key held in a managed key service.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Access control</h3><p>Scoped API credentials (ingest, query, cohort, admin) stored only as salted hashes. Administrative access requires SSO with MFA and is restricted to a private network. Credentials can be rotated and revoked with effect within one minute.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Tenant isolation</h3><p>Organization identity is derived from the credential. PostgreSQL row-level security applies to every PHI table. Dedicated and on-premises deployments add network and compute isolation.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Minimum necessary</h3><p>Models receive de-identified text only. Retrieval is limited to one patient per query. Population queries require a separate credential scope and are logged distinctly.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Audit controls</h3><p>Append-only audit log with database-level revocation of update and delete. Retained for six years. Exportable to your log platform on request.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>No training on your data</h3><p>Customer documents and queries are never used to train or fine-tune models, ours or anyone else's. Model telemetry and third-party tracing are disabled; observability is self-hosted.</p></div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head"><h2>Shared responsibility</h2><p class="lede">HIPAA compliance is a joint outcome. The table below is the same one we review with your compliance officer during onboarding.</p></div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Area</th><th>Arbiter AI</th><th>Your organization</th></tr></thead>
      <tbody>
        <tr><td>Business Associate Agreement</td><td>Signed before any PHI is processed; flow-down BAAs with all subprocessors</td><td>Counter-sign; maintain your own BAAs with other vendors</td></tr>
        <tr><td>Encryption and key management</td><td>Platform encryption, per-tenant keys, rotation</td><td>Protect API credentials; use your own KMS on on-prem deployments</td></tr>
        <tr><td>User identity</td><td>Credential scopes, admin SSO and MFA</td><td>Named users behind each credential; joiner/leaver process</td></tr>
        <tr><td>Audit log review</td><td>Generate, retain, export</td><td>Periodic review per your policy</td></tr>
        <tr><td>Risk analysis</td><td>Our system-level risk analysis, shared under NDA</td><td>Your organizational risk analysis covering use of the service</td></tr>
        <tr><td>Workforce training</td><td>Our staff, annually</td><td>Your staff on appropriate use</td></tr>
        <tr><td>Incident response</td><td>Notification within the contractual window; investigation and remediation</td><td>Your breach assessment and notification obligations</td></tr>
        <tr><td>Clinical decisions</td><td>Never made by the system; answers are evidence with citations</td><td>Human review before any clinical action</td></tr>
      </tbody>
    </table></div>
  </div>
</section>

<section class="on-white" id="baa">
  <div class="wrap grid-2">
    <div>
      <h2>Agreements and attestations</h2>
      <p>We sign a Business Associate Agreement with every customer whose use involves PHI, and we maintain BAAs with each subprocessor that could touch PHI, including cloud infrastructure providers for hosted deployments.</p>
      <p>Our security documentation, system risk analysis, penetration test summary, and subprocessor list are available under NDA. <a href="/contact.html">Request the security package</a>.</p>
    </div>
    <div>
      <h3>Current status</h3>
      <ul class="plain">
        <li style="padding:10px 0;border-top:1px solid var(--line)"><span class="badge">Available</span>&nbsp; Business Associate Agreement</li>
        <li style="padding:10px 0;border-top:1px solid var(--line)"><span class="badge">Available</span>&nbsp; Security overview and architecture review</li>
        <li style="padding:10px 0;border-top:1px solid var(--line)"><span class="badge">Available</span>&nbsp; Independent penetration test summary</li>
        <li style="padding:10px 0;border-top:1px solid var(--line)"><span class="badge gold">In progress</span>&nbsp; SOC 2 Type II</li>
        <li style="padding:10px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)"><span class="badge gold">Planned</span>&nbsp; HITRUST assessment</li>
      </ul>
      <p class="small" style="margin-top:12px">Update this list as attestations are completed. Do not claim a certification before the report is issued.</p>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head"><h2>Questions compliance teams ask us</h2></div>
    <div style="max-width:800px">
      <details><summary>Where is PHI stored and processed?</summary><p>In the deployment you choose: your own data center, a dedicated environment in the cloud region you specify, or our managed environment in the United States. In all cases the model host has no outbound internet access.</p></details>
      <details><summary>Does any PHI reach a third-party AI provider?</summary><p>By default, no. Models run on infrastructure covered by the deployment's BAA. If you opt into a cloud model provider for escalation, only de-identified text is sent, and that provider is under a BAA as a subprocessor.</p></details>
      <details><summary>How is de-identification validated?</summary><p>We measure recall against planted identifiers in synthetic records and against public annotated clinical corpora, and we run a second detection pass on every generated answer. We share these numbers during the pilot and report them monthly in production.</p></details>
      <details><summary>What happens when a customer leaves?</summary><p>Documents, embeddings, token maps, and checkpoints are deleted according to the contract schedule and a deletion certificate is provided. Audit logs are retained for the legally required period.</p></details>
      <details><summary>Can we bring our own encryption keys?</summary><p>Yes on Dedicated and On-premises plans.</p></details>
    </div>
  </div>
</section>

<section class="cta-band section-tight">
  <div class="wrap"><h2>Get the security package for your review.</h2>
    <div class="actions"><a class="btn btn-primary btn-lg" href="/contact.html">Request documentation</a></div></div>
</section>
"""
