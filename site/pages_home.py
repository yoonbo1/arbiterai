# Page bodies for arbiterai.tech. Each entry: (path, <title>, meta description, body HTML).
CHECK = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'


def ledger(animate=True):
    steps = [
        ("Document received", "Encrypted at rest, tagged to tenant and patient", "0.0 s"),
        ("Text extracted", "Native text, then OCR, then vision model only where needed", "1.8 s"),
        ("PHI removed", "18 identifier classes replaced with reversible tokens", "2.1 s"),
        ("Evidence retrieved", "Scoped to one patient, one organization", "2.4 s"),
        ("Answer verified", "Citations required, leak check passed, grounded 0.94", "4.7 s"),
        ("Audit written", "Who, what, when. Append-only.", "4.7 s"),
    ]
    cls = "" if animate else ' class="done"'
    lis = "".join(
        f'<li{cls}><span class="mark">{CHECK}</span><div><div class="step-name">{n}</div><div class="step-desc">{d}</div></div><span class="step-meta">{m}</span></li>'
        for n, d, m in steps)
    return (f'<div class="ledger"{" data-animate" if animate else ""} aria-label="Chain of custody for one request">'
            f'<div class="ledger-title"><strong>Chain of custody</strong><span>job 7f3a…c21e</span></div><ol>{lis}</ol>'
            f'<div class="ledger-foot"><span>tenant: northgate-clinic</span><span>model host: on-prem</span></div></div>')


HOME = f"""
<section class="hero">
  <div class="wrap hero-grid">
    <div>
      <h1>Every answer your clinical AI gives, with the evidence and the audit trail to stand behind it.</h1>
      <p class="lede">Arbiter AI reads medical documents, scans, and faxes, strips protected health information before any model sees it, and returns cited answers your compliance officer can trace line by line.</p>
      <div class="actions">
        <a class="btn btn-primary btn-lg" href="/contact.html">Request a demo</a>
        <a class="btn btn-ghost btn-lg" href="/product.html">See how it works</a>
      </div>
      <p class="hero-note">Deploys inside your network or in a dedicated environment we run for you. We sign a Business Associate Agreement before any PHI is processed.</p>
    </div>
    {ledger()}
  </div>
</section>

<div class="proof">
  <div class="wrap">
    <div><strong>Zero</strong><span>protected health information reaches a model unmasked</span></div>
    <div><strong>Per patient</strong><span>retrieval boundary, enforced in the database</span></div>
    <div><strong>Every answer</strong><span>carries citations to the source page</span></div>
    <div><strong>6-year</strong><span>audit retention, append-only by design</span></div>
  </div>
</div>

<section>
  <div class="wrap">
    <div class="section-head">
      <p class="kicker">Why an arbiter</p>
      <h2>Language models are persuasive. Healthcare needs them to be accountable.</h2>
      <p class="lede">Most AI tools put the model in charge and hope for the best. Arbiter AI puts a verification layer between your documents and the model, and between the model and your staff. Nothing passes without being checked.</p>
    </div>
    <div class="row">
      <h3>De-identify first, always</h3>
      <div><p>Names, dates, record numbers, addresses, and the rest of the Safe Harbor identifier list are replaced with tokens before extraction results are indexed or a question is sent to a model. The mapping back to real values is encrypted per organization and applied only at the final step, only for the authorized requester.</p></div>
    </div>
    <div class="row">
      <h3>Verify before you answer</h3>
      <div><p>Each response is checked for three things: it cites the passages it used, those passages support the claims, and no identifier has leaked. Responses that fail are retried on a stronger model once, then rejected. Your staff never see an unverified answer.</p></div>
    </div>
    <div class="row">
      <h3>Isolate by construction</h3>
      <div><p>Your organization is identified by your credential, never by a field a client could alter. Row-level security in the database, a per-patient retrieval filter, and per-tenant encryption keys mean isolation does not depend on application code being bug-free.</p></div>
    </div>
    <div class="row">
      <h3>Cost that scales with difficulty, not volume</h3>
      <div><p>Clean PDFs are read for free. Scans go to OCR. Only handwriting, forms, and low-confidence pages reach a vision model. Simple questions are answered by a small model; hard ones escalate. You pay for the difficult minority, not the routine majority.</p></div>
    </div>
  </div>
</section>

<section class="on-ink">
  <div class="wrap">
    <div class="section-head">
      <p class="kicker">What it does</p>
      <h2>Built for the documents that never made it into structured data.</h2>
    </div>
    <div class="grid-3">
      <div class="pillar"><div class="mark-line"></div><h3>Discharge summaries and progress notes</h3><p>Ask what changed between admissions, which medications were stopped and why, or what the follow-up plan says. Answers cite the page.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Faxed referrals and outside records</h3><p>Skewed, stamped, and half-legible pages get OCR and vision extraction, then land in the same searchable record as everything else.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Forms, labs, and imaging reports</h3><p>Checkboxes, tables, and handwritten values are transcribed as structured text so they can be queried, not just stored.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Prior authorization and appeals prep</h3><p>Pull the supporting evidence for a request from a full chart in seconds, with the source pages attached for the reviewer.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Chart review and quality audits</h3><p>Run the same set of questions across a cohort under a separate, logged role. Population queries never mix with patient care access.</p></div>
      <div class="pillar"><div class="mark-line"></div><h3>Your own workflows via API</h3><p>Two endpoints, ingest and query, with idempotent jobs and per-request cost accounting. Integrate with an EHR, an intake tool, or a spreadsheet.</p></div>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="section-head">
      <p class="kicker">Deployment</p>
      <h2>Runs where your data is allowed to be.</h2>
      <p class="lede">The same system, three ways to host it. Move between them without changing your integration.</p>
    </div>
    <div class="flow" style="grid-template-columns:repeat(3,1fr)">
      <div><b>On-premises</b><span>Your hardware, your network, no outbound connection from the model host. We install, you operate, we support.</span></div>
      <div><b>Dedicated cloud</b><span>A single-tenant environment in the cloud region you require, covered by our BAA and the provider's. Nothing shared with other customers.</span></div>
      <div><b>Managed shared</b><span>The fastest start for smaller practices and health-tech teams. Isolation enforced at the database and encryption layer, with the same audit trail.</span></div>
    </div>
  </div>
</section>

<section class="on-white section-tight">
  <div class="wrap">
    <div class="grid-2">
      <div>
        <p class="kicker">How a pilot works</p>
        <h2>Prove it on your documents before you trust it with your patients.</h2>
      </div>
      <ol class="steps">
        <li><h4>Synthetic run</h4><p class="small">We demonstrate the full pipeline on generated records with planted identifiers, and show you the de-identification recall and leak-check results.</p></li>
        <li><h4>Your sample, de-identified</h4><p class="small">You provide 20 to 50 de-identified documents in your real formats. We tune extraction and retrieval and report accuracy on questions you choose.</p></li>
        <li><h4>Controlled production</h4><p class="small">BAA signed, environment hardened, a defined user group, and a review period with your compliance officer before general rollout.</p></li>
      </ol>
    </div>
  </div>
</section>

<section class="cta-band section-tight">
  <div class="wrap">
    <h2>See a chart answered with its evidence attached.</h2>
    <div class="actions">
      <a class="btn btn-primary btn-lg" href="/contact.html">Request a demo</a>
      <a class="btn btn-ghost btn-lg" href="/security.html">Read the security overview</a>
    </div>
  </div>
</section>
"""
