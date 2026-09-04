from pages_home import HOME
from pages_product import PRODUCT, SECURITY
from pages_blog import BLOG_PAGES

PRICING = """
<section class="hero" style="padding-bottom:40px">
  <div class="wrap">
    <p class="kicker">Pricing</p>
    <h1 style="max-width:18ch">Priced by what you process, with the isolation level you need.</h1>
    <p class="lede">All plans include de-identification, verification, citations, and the audit log. The difference is where it runs and how much is dedicated to you.</p>
  </div>
</section>

<section class="section-tight">
  <div class="wrap">
    <div class="tiers">
      <div class="tier">
        <h3>Managed shared</h3>
        <p class="who">Small practices, health-tech teams, and pilots that need to start this month.</p>
        <div class="price">From $1,500<small> / month</small></div>
        <p class="small">Includes 5,000 pages and 20,000 queries. Usage beyond that billed per page and per query.</p>
        <ul>
          <li>Isolation at database and encryption layer</li>
          <li>US hosting, BAA included</li>
          <li>Two API credentials, email support</li>
          <li>Monthly quality and cost report</li>
        </ul>
        <a class="btn btn-ghost" href="/contact.html?plan=shared">Start a pilot</a>
      </div>
      <div class="tier featured">
        <h3>Dedicated cloud</h3>
        <p class="who">Clinics, groups, and vendors with residency requirements or security review.</p>
        <div class="price">From $6,000<small> / month</small></div>
        <p class="small">Includes 50,000 pages and 250,000 queries. Committed-volume discounts available.</p>
        <ul>
          <li>Single-tenant environment in your region</li>
          <li>Bring your own encryption keys</li>
          <li>SSO, webhooks, SIEM export</li>
          <li>Named support engineer, 99.9% uptime SLA</li>
        </ul>
        <a class="btn btn-brass" href="/contact.html?plan=dedicated">Talk to us</a>
      </div>
      <div class="tier">
        <h3>On-premises</h3>
        <p class="who">Hospitals and systems that keep PHI inside their own walls.</p>
        <div class="price">Annual license</div>
        <p class="small">Priced by GPU nodes and page volume. Installation and hardening included.</p>
        <ul>
          <li>Runs on your hardware, no outbound access</li>
          <li>Your KMS, your identity provider</li>
          <li>Quarterly model and security updates</li>
          <li>Onsite or remote support options</li>
        </ul>
        <a class="btn btn-ghost" href="/contact.html?plan=onprem">Request a quote</a>
      </div>
    </div>
    <p class="small" style="margin-top:20px">Prices are starting points for planning and are confirmed in a written proposal after a scoping call. Pilot fees are credited toward the first year on annual contracts.</p>
  </div>
</section>

<section class="on-white">
  <div class="wrap">
    <div class="section-head"><h2>Usage pricing</h2><p class="lede">Beyond plan allowances. Pages are billed by extraction route, because that is where cost actually differs.</p></div>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Unit</th><th>Managed shared</th><th>Dedicated cloud</th><th>What it covers</th></tr></thead>
      <tbody>
        <tr><td>Page, native text</td><td>$0.01</td><td>$0.008</td><td>PDFs with a text layer</td></tr>
        <tr><td>Page, OCR</td><td>$0.03</td><td>$0.024</td><td>Clean scans and faxes</td></tr>
        <tr><td>Page, vision</td><td>$0.12</td><td>$0.09</td><td>Forms, tables, handwriting, poor scans</td></tr>
        <tr><td>Query, standard</td><td>$0.02</td><td>$0.015</td><td>Answered by the small model</td></tr>
        <tr><td>Query, escalated</td><td>$0.10</td><td>$0.08</td><td>Required the large model to pass verification</td></tr>
        <tr><td>Storage</td><td>$0.50 / GB-month</td><td>$0.40 / GB-month</td><td>Encrypted documents and index</td></tr>
      </tbody>
    </table></div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head"><h2>Pricing questions</h2></div>
    <div style="max-width:800px">
      <details><summary>What does a pilot cost?</summary><p>A four-week pilot on your de-identified sample is a fixed fee, typically $5,000 to $15,000 depending on document complexity and integration work. It is credited toward an annual contract.</p></details>
      <details><summary>How do I estimate my page mix?</summary><p>Send us a de-identified sample of 50 documents and we will run the router and report the exact split. As a rule of thumb, clinics with mostly electronic records see 10 to 20 percent vision pages; those with heavy fax intake see 25 to 40 percent.</p></details>
      <details><summary>Are there per-user fees?</summary><p>No. Pricing is by usage and deployment, not seats.</p></details>
      <details><summary>Can we cap spend?</summary><p>Yes. Every credential has a rate limit, and plans can have a hard monthly cap that pauses processing rather than overbilling.</p></details>
    </div>
  </div>
</section>

<section class="cta-band section-tight">
  <div class="wrap"><h2>Get a proposal for your volume.</h2>
    <div class="actions"><a class="btn btn-primary btn-lg" href="/contact.html">Contact sales</a></div></div>
</section>
"""

DOCS = """
<section class="hero" style="padding-bottom:40px">
  <div class="wrap">
    <p class="kicker">Documentation</p>
    <h1 style="max-width:16ch">Quickstart</h1>
    <p class="lede">From credential to first cited answer in about ten minutes. This guide uses synthetic data; do not send real PHI until your BAA is executed and your environment is confirmed.</p>
  </div>
</section>

<section class="on-white">
  <div class="wrap prose">
    <ol class="steps">
      <li><h4>Get a credential</h4><p>Your administrator creates credentials in the console, or on on-premises deployments via the admin API. A credential looks like <code>hipaa_live_…</code>, is shown once, and carries scopes such as <code>ingest</code> and <code>query</code>. Store it in a secrets manager, never in source code.</p></li>
      <li><h4>Submit a document</h4>
<pre><code>curl -X POST https://&lt;your-deployment&gt;/v1/documents \\
  -H "Authorization: Bearer $ARBITER_KEY" \\
  -H "Idempotency-Key: demo-0001" \\
  -H "Content-Type: application/json" \\
  -d '{"patient_external_id":"DEMO-001","doc_type":"discharge_summary",
       "storage_uri":"s3://your-bucket/demo/dc-summary.pdf"}'</code></pre>
<p>Replace <code>&lt;your-deployment&gt;</code> with the hostname of your Arbiter AI deployment; there is no shared public API.</p>
<p>The response is <code>202 Accepted</code> with a <code>job_id</code>. Ingestion is asynchronous; poll the job or configure a webhook.</p></li>
      <li><h4>Ask a question</h4>
<pre><code>curl -X POST https://&lt;your-deployment&gt;/v1/queries \\
  -H "Authorization: Bearer $ARBITER_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"patient_external_id":"DEMO-001",
       "question":"What was the most recent HbA1c and when was it drawn?"}'</code></pre></li>
      <li><h4>Read the result</h4>
<pre><code>curl https://&lt;your-deployment&gt;/v1/jobs/$JOB_ID -H "Authorization: Bearer $ARBITER_KEY"

{"status":"done",
 "result":{"answer":"The most recent HbA1c was 7.4%, drawn on the day of admission [3].",
           "citations":[3],
           "validation":{"grounded":0.96,"cites_chunks":true,"phi_leak":false}}}</code></pre>
<p>Citation numbers refer to passages you can fetch with their page number, so a reviewer can open the source document at the right place.</p></li>
    </ol>

    <h2>Concepts</h2>
    <h3>Organizations and patients</h3>
    <p>Your organization is identified by your credential. Patients are identified by an <code>external_id</code> you choose, typically your MRN. Queries are always scoped to one patient; cross-patient queries require the <code>cohort</code> scope and a separate endpoint.</p>
    <h3>Idempotency</h3>
    <p>Send an <code>Idempotency-Key</code> on every POST. Retrying with the same key returns the original job instead of creating a duplicate, so network failures never double-process or double-bill.</p>
    <h3>Job states</h3>
    <p><code>queued</code>, <code>processing</code>, <code>done</code>, <code>failed</code>. A <code>failed</code> query includes a <code>validation</code> object explaining why it was rejected rather than returning an unverified answer.</p>
    <h3>Rate limits</h3>
    <p>Each credential has a per-minute limit set by your administrator. Exceeding it returns <code>429</code>. Bursts should be queued on your side or spread across credentials.</p>

    <h2>Errors</h2>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Status</th><th>Meaning</th></tr></thead>
      <tbody>
        <tr><td>401</td><td>Missing, expired, or revoked credential</td></tr>
        <tr><td>403</td><td>Credential lacks the required scope, or organization has no executed BAA</td></tr>
        <tr><td>404</td><td>Job not found, including jobs belonging to another organization</td></tr>
        <tr><td>422</td><td>Request body failed validation</td></tr>
        <tr><td>429</td><td>Rate limit exceeded</td></tr>
      </tbody>
    </table></div>

    <div class="callout"><p>Need webhooks, SIEM export, or the on-premises install guide? Those are provided during onboarding for Dedicated and On-premises plans. <a href="/contact.html">Contact us</a>.</p></div>
  </div>
</section>
"""

ABOUT = """
<section class="hero" style="padding-bottom:40px">
  <div class="wrap">
    <p class="kicker">About</p>
    <h1 style="max-width:18ch">We build the part of clinical AI that says no.</h1>
    <p class="lede">Arbiter AI started from a simple observation: the hard part of putting language models in healthcare is not getting them to answer. It is getting them to answer only when they can prove it, and never with information they should not have seen.</p>
  </div>
</section>

<section class="on-white">
  <div class="wrap grid-2">
    <div>
      <h2>What we believe</h2>
      <p>Verification should be structural. If isolation depends on a developer remembering a filter, it will eventually fail. If de-identification is optional, it will eventually be skipped. We build these as constraints the system cannot operate without.</p>
      <p>Evidence beats confidence. An answer without a citation is an opinion. Our system returns passages and page numbers, and rejects its own output when the passages do not support it.</p>
      <p>Cost discipline is a safety feature. Systems that are expensive to run get bypassed. Routing routine work to inexpensive paths is what makes it possible to keep the expensive checks on every request.</p>
    </div>
    <div>
      <h2>How we work with customers</h2>
      <p>Every engagement begins with a pilot on your own document formats, with acceptance criteria you set. We share our security documentation under NDA before you commit, and we review the shared-responsibility model with your compliance officer during onboarding.</p>
      <p>We are a software vendor. We do not provide medical advice, and our system does not make clinical decisions. It gives your staff faster access to what is already in the record, with the evidence attached.</p>
    </div>
  </div>
</section>

<section class="cta-band section-tight">
  <div class="wrap"><h2>Talk to the people who built it.</h2>
    <div class="actions"><a class="btn btn-primary btn-lg" href="/contact.html">Get in touch</a></div></div>
</section>
"""

CONTACT = """
<section class="hero" style="padding-bottom:40px">
  <div class="wrap hero-grid" style="align-items:start">
    <div>
      <p class="kicker">Contact</p>
      <h1 style="max-width:14ch">Request a demo or the security package.</h1>
      <p class="lede">Tell us about your documents and where they need to live. We reply within one business day, and the first call is a scoping conversation, not a pitch.</p>
      <p>Prefer email? <a href="mailto:hello@arbiterai.tech">hello@arbiterai.tech</a></p>
      <p class="small">Please do not include protected health information in this form or in email. We will set up a secure channel for any sample documents.</p>
    </div>
    <div>
      <form data-demo-form data-ajax name="demo" method="POST" action="/submit">
        <p style="display:none"><label>Leave blank <input name="company-site"></label></p>
        <p class="form-note">Fields marked <span class="req">*</span> are required.</p>
        <div class="form-2">
          <label><span>Full name <span class="req" aria-hidden="true">*</span></span><input name="name" required autocomplete="name"></label>
          <label><span>Work email <span class="req" aria-hidden="true">*</span></span><input name="email" type="email" required autocomplete="email"></label>
        </div>
        <div class="form-2">
          <label><span>Organization <span class="req" aria-hidden="true">*</span></span><input name="org" required autocomplete="organization"></label>
          <label>Role<input name="role" placeholder="e.g. CTO, Compliance Officer"></label>
        </div>
        <label>What are you interested in?
          <select name="interest">
            <option>Product demo</option><option>Security package (under NDA)</option><option>Pilot pricing</option><option>On-premises deployment</option><option>Partnership</option>
          </select></label>
        <div class="form-2">
          <label>Approximate pages per month
            <select name="volume"><option>Under 5,000</option><option>5,000 to 50,000</option><option>50,000 to 500,000</option><option>Over 500,000</option><option>Not sure yet</option></select></label>
          <label>Hosting requirement
            <select name="hosting"><option>No preference</option><option>Dedicated cloud, US</option><option>Dedicated cloud, other region</option><option>On-premises only</option></select></label>
        </div>
        <label>Anything else<textarea name="message" placeholder="Document types, systems you use, timelines. No PHI please."></textarea></label>
        <label class="consent"><input type="checkbox" name="consent" required><span class="small">I agree to be contacted about my request and have read the <a href="/privacy.html">privacy policy</a>. <span class="req" aria-hidden="true">*</span></span></label>
        <div><button class="btn btn-primary btn-lg" type="submit">Request a demo</button></div>
      </form>
      <div class="form-ok"><strong>Thank you.</strong> We have your request and will reply within one business day.</div>
      <div class="form-error"><strong>That did not go through.</strong> Please email <a href="mailto:hello@arbiterai.tech">hello@arbiterai.tech</a> and we will reply within one business day.</div>
    </div>
  </div>
</section>
"""

PRIVACY = """
<section class="section-tight"><div class="wrap prose">
<p class="kicker">Legal</p><h1>Privacy policy</h1>
<p class="small">Last updated: September 3, 2026.</p>
<h2>Who we are</h2><p>Arbiter AI ("we", "us") operates arbiterai.tech and the Arbiter AI service. Contact: hello@arbiterai.tech.</p>
<h2>Website visitors</h2><p>We collect information you submit through forms (name, email, organization, message) to respond to your request. We use privacy-respecting analytics that do not use cookies to identify you across sites. We do not sell personal information.</p>
<h2>Customer data and protected health information</h2><p>When a customer uses the Arbiter AI service to process documents that contain protected health information, we act as a business associate under HIPAA and process that information only as permitted by our Business Associate Agreement and the customer's instructions. We do not use customer documents or queries to train models. Customer data is deleted at contract end according to the agreed schedule, except audit records retained as required by law.</p>
<h2>Subprocessors</h2><p>We use infrastructure and support providers under written agreements, including business associate agreements where PHI may be involved. A current list is available on request.</p>
<h2>Security</h2><p>See our <a href="/security.html">security overview</a>. No method of transmission or storage is completely secure; we notify customers of security incidents as required by contract and law.</p>
<h2>Your rights</h2><p>Depending on where you live, you may have rights to access, correct, or delete personal information we hold about you as a website visitor or contact. Email hello@arbiterai.tech. For information processed on behalf of a healthcare customer, contact that organization directly; we will assist them in responding.</p>
<h2>Changes</h2><p>We will post updates on this page and change the date above.</p>
</div></section>
"""

TERMS = """
<section class="section-tight"><div class="wrap prose">
<p class="kicker">Legal</p><h1>Terms of service</h1>
<p class="small">Last updated: September 3, 2026. Customers are governed by their signed order form, master agreement, and Business Associate Agreement, which take precedence over these website terms.</p>
<h2>Use of this website</h2><p>Content on arbiterai.tech is provided for information. You may not scrape, reverse engineer, or attempt to access non-public areas of the site or service.</p>
<h2>No medical advice</h2><p>Arbiter AI is software that retrieves and summarizes information from documents supplied by customers. It does not provide medical advice, diagnosis, or treatment recommendations, and its output must be reviewed by qualified personnel before any clinical action.</p>
<h2>Service terms</h2><p>Access to the Arbiter AI service requires a signed agreement, which sets out acceptable use, service levels, data handling, fees, warranties, and limitations of liability. Processing of protected health information additionally requires an executed Business Associate Agreement.</p>
<h2>Intellectual property</h2><p>The Arbiter AI name, logo, and website content are our property. Customer documents and data remain the customer's property.</p>
<h2>Disclaimer and limitation</h2><p>The website is provided "as is". To the extent permitted by law, we disclaim warranties regarding the website and are not liable for indirect or consequential damages arising from its use.</p>
<h2>Governing law</h2><p>Governing law and venue for the Arbiter AI service are set out in your signed agreement with us, which controls in the event of any conflict with these website terms. For questions about these terms, contact <a href="mailto:hello@arbiterai.tech">hello@arbiterai.tech</a>.</p>
</div></section>
"""

NOTFOUND = """
<section><div class="wrap center"><h1>Page not found</h1><p class="lede">The page you asked for does not exist or has moved.</p><a class="btn btn-primary" href="/">Back to the home page</a></div></section>
"""

PAGES = [
    ("index.html", "Arbiter AI — Private, verified AI for clinical documents",
     "HIPAA-ready document AI that de-identifies before any model sees the data, cites every answer, and keeps a six-year audit trail. On-premises or dedicated cloud under a BAA.", HOME),
    ("product.html", "How Arbiter AI works — ingestion, retrieval, verification",
     "From scanned page to cited answer: cost-aware extraction, de-identification, patient-scoped retrieval, and a verification gate on every response.", PRODUCT),
    ("security.html", "Security and compliance — Arbiter AI",
     "Encryption, tenant isolation, audit controls, shared-responsibility model, and our BAA. What we have, and what is in progress.", SECURITY),
    ("pricing.html", "Pricing — Arbiter AI",
     "Managed shared, dedicated cloud, and on-premises plans priced by pages processed and queries answered.", PRICING),
    ("docs.html", "Documentation and quickstart — Arbiter AI",
     "Submit a document, ask a question, read a cited answer. API reference for the Arbiter AI service.", DOCS),
    ("about.html", "About Arbiter AI",
     "We build the verification layer for clinical AI: structural isolation, mandatory citations, and de-identification by default.", ABOUT),
    # Blog index and one entry per post. Each carries a meta dict (og:type, sitemap
    # lastmod, JSON-LD) that build.py's render() folds into the shared shell.
    *BLOG_PAGES,
    ("contact.html", "Request a demo — Arbiter AI",
     "Request a demo, pilot pricing, or the security package for your compliance review.", CONTACT),
    ("privacy.html", "Privacy policy — Arbiter AI", "How Arbiter AI handles website visitor data and customer data.", PRIVACY),
    ("terms.html", "Terms of service — Arbiter AI", "Website terms for arbiterai.tech.", TERMS),
    ("404.html", "Page not found — Arbiter AI", "Page not found.", NOTFOUND),
]
