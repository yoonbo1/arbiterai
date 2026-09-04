"""Blog: post metadata, the article bodies, and the generated index page.

Same convention as pages.py — bodies are plain HTML strings. Everything a crawler needs
(JSON-LD, article meta tags, RSS) is derived from POSTS so there is one source of truth.
`__SITE__` in a head fragment is replaced with the canonical origin by build.py.

The six diagrams in the source article were vector drawings. They are rebuilt here as
inline SVG and CSS in the site palette so they scale, reflow on a phone, and stay readable
to a crawler.
"""
import json
import re
from pathlib import Path

PDF_FILE = Path(__file__).parent / "assets" / "medical-record-acronyms.pdf"
PDF_SIZE = f"{PDF_FILE.stat().st_size / 1024:,.0f} KB" if PDF_FILE.exists() else ""

# ---------------------------------------------------------------------------- diagrams

TIMELINE_TERMS = [
    ("1893", "ICD", "International Classification of Diseases",
     "Standard codes for diagnoses. Began as a list of causes of death."),
    ("1907", "MRN", "Medical Record Number",
     "The unique ID a hospital gives each patient. Ties every sheet to one person."),
    ("1966", "CPT", "Current Procedural Terminology",
     "Standard codes for what a clinician did. Used on every claim."),
    ("1968", "SOAP", "Subjective, Objective, Assessment, Plan",
     "The four-part structure of a clinical note."),
    ("1972", "EMR / EHR", "Electronic Medical / Health Record",
     "The patient chart kept in software instead of on paper."),
    ("1987", "HL7", "Health Level Seven",
     "The messaging standard hospital systems use to talk to each other."),
    ("1996", "HIPAA", "Health Insurance Portability and Accountability Act",
     "The US law whose Privacy and Security Rules govern health data."),
    ("2000", "PHI", "Protected Health Information",
     "Any health data that can identify a patient. What HIPAA protects."),
    ("2000", "Safe Harbor", "HIPAA de-identification method",
     "Remove 18 listed identifiers and the data is no longer PHI."),
    ("2003", "BAA", "Business Associate Agreement",
     "The contract required with any vendor that handles PHI."),
    ("2007", "NPI", "National Provider Identifier",
     "A single public ten-digit number for every clinician and organization."),
    ("2009", "HITECH", "Health Information Technology for Economic and Clinical Health Act",
     "Paid hospitals to adopt EHRs and made vendors directly liable for breaches."),
    ("2011", "FHIR", "Fast Healthcare Interoperability Resources",
     "A web API standard for reading and writing health records."),
    ("2015", "ICD-10-CM", "ICD, 10th revision, Clinical Modification",
     "The diagnosis code set the US switched to on October 1, 2015."),
]

HIPAA_STEPS = [
    ("1996", "Statute signed", "an insurance bill about job lock"),
    ("1999", "Privacy rule proposed", "Congress missed its deadline; 52,000+ comments"),
    ("2003", "Privacy Rule in effect", "PHI defined, Safe Harbor written, BAAs required"),
    ("2005", "Security Rule in effect", "safeguards for electronic PHI"),
    ("2006", "Enforcement Rule", "penalties finally usable"),
    ("2009", "HITECH Act", "vendors directly liable, breach notification"),
    ("2013", "Omnibus Rule", "subcontractors inside the fence"),
]


def _timeline(rows):
    out = []
    for year, name, sub, desc in rows:
        out.append(
            f'<li><span class="yr">{year}</span><div class="tl"><b>{name}</b>'
            f'<em>{sub}</em><p>{desc}</p></div></li>')
    return '<ol class="post-timeline">' + "".join(out) + "</ol>"


FIG_TIMELINE = (
    '<figure class="post-fig">'
    '<p class="post-fig-head">The year each term began</p>'
    + _timeline(TIMELINE_TERMS) +
    '<figcaption>Each term with the year it started, what it stands for, and what it '
    'does.</figcaption></figure>')

FIG_HIPAA = (
    '<figure class="post-fig">'
    '<p class="post-fig-head">Seven years from signing to a rule anyone had to follow</p>'
    + '<ol class="post-timeline post-timeline-plain">' + "".join(
        f'<li><span class="yr">{y}</span><div class="tl"><b>{n}</b><p>{d}</p></div></li>'
        for y, n, d in HIPAA_STEPS) + '</ol>' +
    '<figcaption>The rules people mean by "HIPAA" arrived years after the law '
    'itself.</figcaption></figure>')

# Two small SVGs: who a regulator could reach before 2009, and after. Arrowheads get
# per-diagram marker ids because both drawings live in the same document.
_REACH_DEFS = ('<defs><marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" '
               'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
               '<path d="M0 0 L10 5 L0 10 z" fill="{fill}"/></marker></defs>')

FIG_REACH = (
    '<figure class="post-fig">'
    '<div class="grid-2 post-compare">'

    '<div class="post-panel"><p class="post-panel-year">Before 2009</p>'
    '<svg class="post-svg" viewBox="0 0 300 176" role="img" '
    'aria-label="Before 2009: HHS reaches the hospital. The hospital holds a contract with '
    'the vendor. The subcontractor is out of scope.">'
    + _REACH_DEFS.format(mid="reach-a", fill="#172033") +
    '<rect class="bx" x="4" y="14" width="76" height="30" rx="4"/>'
    '<text class="lb" x="42" y="33">HHS</text>'
    '<rect class="bx" x="186" y="14" width="104" height="30" rx="4"/>'
    '<text class="lb" x="238" y="33">Hospital</text>'
    '<line class="ln" x1="86" y1="29" x2="178" y2="29" marker-end="url(#reach-a)"/>'
    '<line class="ln dot" x1="238" y1="50" x2="238" y2="76"/>'
    '<text class="mut" x="246" y="68">contract only</text>'
    '<rect class="bx" x="186" y="80" width="104" height="30" rx="4"/>'
    '<text class="lb" x="238" y="99">Vendor</text>'
    '<rect class="bx out" x="186" y="132" width="104" height="30" rx="4"/>'
    '<text class="lb mut" x="238" y="151">Subcontractor</text>'
    '<text class="mut" x="180" y="151" text-anchor="end">out of scope</text>'
    '</svg>'
    '<p class="small">the vendor answers to the hospital, not to the regulator</p></div>'

    '<div class="post-panel"><p class="post-panel-year">After HITECH and Omnibus</p>'
    '<svg class="post-svg" viewBox="0 0 300 176" role="img" '
    'aria-label="After HITECH and the Omnibus Rule: HHS reaches the hospital, the vendor '
    'and the subcontractor directly.">'
    + _REACH_DEFS.format(mid="reach-b", fill="#2F7F6E") +
    '<rect class="bx" x="4" y="14" width="76" height="30" rx="4"/>'
    '<text class="lb" x="42" y="33">HHS</text>'
    '<path class="ln go" d="M86 29 H178" marker-end="url(#reach-b)"/>'
    '<path class="ln go" d="M112 29 V95 H178" marker-end="url(#reach-b)"/>'
    '<path class="ln go" d="M112 95 V147 H178" marker-end="url(#reach-b)"/>'
    '<rect class="bx" x="186" y="14" width="104" height="30" rx="4"/>'
    '<text class="lb" x="238" y="33">Hospital</text>'
    '<rect class="bx" x="186" y="80" width="104" height="30" rx="4"/>'
    '<text class="lb" x="238" y="99">Vendor</text>'
    '<rect class="bx" x="186" y="132" width="104" height="30" rx="4"/>'
    '<text class="lb" x="238" y="151">Subcontractor</text>'
    '</svg>'
    '<p class="small">directly liable, all three</p></div>'

    '</div>'
    '<figcaption>Before 2009, regulators could reach only the hospital. After HITECH and '
    'the Omnibus Rule, they can reach the vendor and its subcontractors '
    'directly.</figcaption></figure>')


def _bar(value, period, tone=""):
    height = value / 14.2 * 100
    return (f'<div class="post-bar"><div class="post-bar-track">'
            f'<span class="post-bar-fill{tone}" style="height:{height:.1f}%">'
            f'<b>{value}</b></span></div><span class="post-bar-x">{period}</span></div>')


FIG_BARS = (
    '<figure class="post-fig">'
    '<p class="post-fig-head">Annual increase in EHR adoption, percentage points per year</p>'
    '<div class="grid-2 post-bars">'
    '<div class="post-bar-group">'
    '<div class="post-bar-cols">'
    + _bar(3.2, "2008 to 2010") + _bar(14.2, "2011 to 2015", " hi") +
    '</div><p class="post-bar-label">Eligible for incentives</p></div>'
    '<div class="post-bar-group">'
    '<div class="post-bar-cols">'
    + _bar(0.1, "2008 to 2010") + _bar(3.3, "2011 to 2015") +
    '</div><p class="post-bar-label">Not eligible</p></div>'
    '</div>'
    '<figcaption>Hospitals eligible for HITECH payments adopted electronic records about '
    'four times faster after 2011. Ineligible hospitals barely moved.</figcaption></figure>')

# ---------------------------------------------------------------------------- article

ARTICLE = r"""
<article>
<section class="hero" style="padding-bottom:40px">
  <div class="wrap">
    <p class="kicker">Blog</p>
    <h1 style="max-width:22ch">Medical record acronyms: what each one means and why it exists</h1>
    <p class="lede">Fourteen terms you will meet in any healthcare product. For each: what it is, where it came from, and why it matters to the software.</p>
    <p class="post-meta"><time datetime="2026-09-03">September 3, 2026</time><span aria-hidden="true">&middot;</span>About a ten minute read</p>
    <p class="actions"><a class="btn btn-ghost" href="/assets/medical-record-acronyms.pdf" type="application/pdf" download>Download as PDF</a> <span class="small">PDF, __PDF_SIZE__</span></p>
  </div>
</section>

<section class="section-tight"><div class="wrap prose post-body">

__FIG_TIMELINE__

<p>These are listed in the order they were created. The technology terms (scanning, text extraction, AI models) are left out on purpose. Everything here would still exist if computers didn't.</p>

<h2 id="icd">ICD</h2>
<p class="post-expansion">International Classification of Diseases, 1893</p>
<p><strong>What it is:</strong> the standard code set for diagnoses. "E11.65" means type 2 diabetes with high blood sugar. Every diagnosis in a chart or on a claim is an ICD code.</p>
<p><strong>Where it came from:</strong> a statistician in Paris, Jacques Bertillon, was asked to make a list of causes of death that countries could compare. It was adopted in 1893 and the US started using it in 1898, with an update every ten years. In 1948 the World Health Organization took it over and expanded it from causes of death to all diseases. The US used its own version, ICD-9-CM, for far longer than most countries and only switched to ICD-10-CM on October 1, 2015.</p>

<figure class="post-fig">
  <div class="grid-2 post-compare">
    <div class="post-panel">
      <p class="post-panel-year">1893</p>
      <h3 class="post-panel-title">International List of Causes of Death</h3>
      <ol class="post-causes"><li>Typhoid fever</li><li>Typhus</li><li>Relapsing fever</li><li>Malaria</li><li>Smallpox</li></ol>
      <p class="small">&hellip; 179 groups, mortality only</p>
    </div>
    <div class="post-panel">
      <p class="post-panel-year">2015</p>
      <p class="post-code-big">E11.65</p>
      <dl class="post-split">
        <div><dt>E</dt><dd>chapter E, endocrine</dd></div>
        <div><dt>11</dt><dd>type 2 diabetes</dd></div>
        <div><dt>.65</dt><dd>with hyperglycemia</dd></div>
      </dl>
      <p class="small">tens of thousands of codes, morbidity and billing</p>
    </div>
  </div>
  <figcaption>Bertillon's 1893 list had 179 causes of death. A modern ICD-10-CM code packs the chapter, the condition, and the complication into one string.</figcaption>
</figure>

<div class="callout"><p><strong>Why it matters:</strong> a diagnosis code is structured data you can rely on, unlike free text. It is also a clue to what is in the note.</p></div>

<h2 id="mrn">MRN</h2>
<p class="post-expansion">Medical Record Number, 1907</p>
<p><strong>What it is:</strong> the unique ID a hospital assigns to each patient. Every document about that patient carries it.</p>
<p><strong>Where it came from:</strong> until 1907, doctors at the Mayo Clinic each kept their own notebook. A patient who saw two doctors had two unrelated records. Henry Plummer, a physician who had wanted to be an engineer, replaced this with one folder per patient, kept in a central file, with a number stamped on every sheet. Patient number 000-001 was entered on July 19, 1907. Every hospital record system since has copied the idea.</p>

<figure class="post-fig">
  <div class="grid-2 post-compare">
    <div class="post-panel">
      <p class="post-panel-year">Before 1907</p>
      <ul class="post-cards"><li>Dr. A's ledger</li><li>Dr. B's ledger</li><li>Lab book</li></ul>
      <p class="small">same patient, three places, three owners</p>
    </div>
    <div class="post-panel">
      <p class="post-panel-year">After 1907</p>
      <ul class="post-cards post-cards-stamped"><li>000-001</li><li>000-001</li><li>000-001</li></ul>
      <p class="small">one folder, the same number on every sheet, shared by every department</p>
    </div>
  </div>
  <figcaption>Before: each doctor kept separate notes on the same patient. After: one numbered folder that every department files into.</figcaption>
</figure>

<div class="callout"><p><strong>Why it matters:</strong> an MRN identifies a patient directly, so it counts as protected information and has to be removed when data is de-identified (see Safe Harbor below).</p></div>

<h2 id="cpt">CPT</h2>
<p class="post-expansion">Current Procedural Terminology, 1966</p>
<p><strong>What it is:</strong> the standard code set for procedures and services. ICD says what was wrong; CPT says what the clinician did about it.</p>
<p><strong>Where it came from:</strong> the American Medical Association published the first edition in 1966 so that a service meant the same thing to every insurer. The AMA still owns and licenses it.</p>

<div class="callout"><p><strong>Why it matters:</strong> ICD plus CPT is the language of billing. In a hospital, "coding" means assigning these codes, not writing software.</p></div>

<h2 id="soap">SOAP</h2>
<p class="post-expansion">Subjective, Objective, Assessment, Plan, 1968</p>
<p><strong>What it is:</strong> the standard structure of a clinical note. What the patient reports, what the clinician measured, what the clinician thinks is going on, and what happens next.</p>
<p><strong>Where it came from:</strong> Lawrence Weed, a physician in Vermont, published a paper in 1968 arguing that medical notes were so disorganized you could not tell whether the doctor had reasoned clearly. He proposed organizing the chart around a numbered list of problems, with a four-part note for each one. The full system was too much work and mostly did not catch on. The four-part note did.</p>

<figure class="post-fig">
  <div class="grid-2 post-compare">
    <div class="post-panel">
      <p class="post-panel-year">A note, before Weed</p>
      <div class="post-scribble" aria-hidden="true"><span style="width:96%"></span><span style="width:74%"></span><span style="width:99%"></span><span style="width:56%"></span><span style="width:88%"></span><span style="width:81%"></span><span style="width:47%"></span></div>
      <p class="small">everything, in the order it occurred to the writer</p>
    </div>
    <div class="post-panel">
      <p class="post-panel-year">SOAP, 1968</p>
      <dl class="post-soap">
        <div><dt>S</dt><dd>what the patient says</dd></div>
        <div><dt>O</dt><dd>what you measured</dd></div>
        <div><dt>A</dt><dd>what you think it is</dd></div>
        <div><dt>P</dt><dd>what you'll do</dd></div>
      </dl>
      <p class="small">the reasoning becomes visible</p>
    </div>
  </div>
  <figcaption>A free-text note versus a SOAP note. The structure makes the clinician's reasoning visible.</figcaption>
</figure>

<div class="callout"><p><strong>Why it matters:</strong> most notes you will parse follow this shape, even when the headings are missing. Knowing it helps you find the assessment and the plan.</p></div>

<h2 id="emr-ehr">EMR and EHR</h2>
<p class="post-expansion">Electronic Medical Record, Electronic Health Record, 1972</p>
<p><strong>What it is:</strong> the patient chart kept in software. The two terms are used interchangeably. Strictly, a medical record is one organization's chart and a health record is meant to follow the patient across organizations.</p>
<p><strong>Where it came from:</strong> several groups built early versions in the late 1960s and early 1970s. The one most often credited is the Regenstrief Institute in Indianapolis, which in 1972 built a system that pulled lab and pharmacy data into one record automatically. The Veterans Administration started its own system around the same time. Adoption stayed low for decades because computing was expensive; in the late 1960s a megabyte of memory cost about a thousand dollars.</p>

<div class="callout"><p><strong>Why it matters:</strong> the EHR is where the data lives. Reading from it and writing back to it is most of the integration work.</p></div>

<h2 id="hl7">HL7</h2>
<p class="post-expansion">Health Level Seven, 1987</p>
<p><strong>What it is:</strong> the messaging standard hospital systems use to talk to each other. An HL7 message says things like "this patient was admitted" or "this lab result is ready."</p>
<p><strong>Where it came from:</strong> once a hospital had a lab system, a pharmacy system, and an admissions system from different vendors, they needed a shared message format. A group of volunteers founded HL7 in 1987 to define one. The "seven" refers to the application layer of the network stack: the standard is about what messages mean, not how they travel. HL7 version 2, from that era, is still the most common interface in healthcare. Version 3 was more rigorous and mostly went unused.</p>

<div class="callout"><p><strong>Why it matters:</strong> if your product receives data from a hospital, there is a good chance it arrives as HL7 v2 messages.</p></div>

<h2 id="hipaa">HIPAA</h2>
<p class="post-expansion">Health Insurance Portability and Accountability Act, 1996</p>
<p><strong>What it is:</strong> the US law whose Privacy Rule and Security Rule govern how health data is used and protected.</p>
<p><strong>Where it came from:</strong> it started as an insurance law. Its main goal was letting people change jobs without losing coverage. Because that raised insurers' costs, Congress added rules to cut fraud and standardize claims processing. Privacy was a late addition: the law said that if Congress did not pass a health privacy law within three years, HHS had to write regulations itself. Congress did not, so HHS did.</p>
<p>The Privacy Rule took effect in 2003 and the Security Rule in 2005. Real enforcement started in 2006. Later laws (HITECH in 2009, the Omnibus Rule in 2013) added breach notification and extended liability to vendors.</p>

__FIG_HIPAA__

<div class="callout"><p><strong>Why it matters:</strong> there is no HIPAA certification. The law never created one. A product can be built to satisfy the rules, but nobody can certify it.</p></div>

<h2 id="phi">PHI</h2>
<p class="post-expansion">Protected Health Information, 2000</p>
<p><strong>What it is:</strong> any health information that can be tied to a person. Names, dates, record numbers, and the medical content attached to them. ePHI is the same thing in electronic form, which is what the Security Rule covers.</p>
<p><strong>Where it came from:</strong> the Privacy Rule needed a defined term for what it protected. The formal phrase is "individually identifiable health information." PHI is the short form everyone uses.</p>

<div class="callout"><p><strong>Why it matters:</strong> PHI is the thing that must not leak, must not be logged carelessly, and must not reach a model or a vendor without safeguards.</p></div>

<h2 id="safe-harbor">Safe Harbor</h2>
<p class="post-expansion">HIPAA de-identification method, 2000</p>
<p><strong>What it is:</strong> the rule for turning PHI into non-PHI. Remove eighteen types of identifiers and have no reason to believe the rest could identify anyone, and the data is no longer protected.</p>
<p><strong>Where it came from:</strong> in 1997, MIT graduate student Latanya Sweeney showed why removing names is not enough. Massachusetts had released hospital records with names and addresses stripped. Sweeney bought the Cambridge voter list for twenty dollars and matched the two datasets on ZIP code, birth date, and sex. Only six voters shared the governor's birthday; three were men; one lived in his ZIP code. She mailed the governor his own medical file.</p>

<figure class="post-fig">
  <ol class="post-funnel">
    <li style="width:100%"><span>Cambridge voter roll, bought for $20</span><b class="note">every registered voter</b></li>
    <li style="width:80%"><span>share the governor's birth date</span><b>6</b></li>
    <li style="width:62%"><span>of those, male</span><b>3</b></li>
    <li class="last" style="width:46%"><span>in his ZIP code</span><b>1</b></li>
  </ol>
  <figcaption>Three fields, none of them a name, narrowed a whole city to one person.</figcaption>
</figure>

<p>Her research showed that about 87 percent of Americans can be identified from just those three fields. The Safe Harbor list is a direct response. It removes names, any geography smaller than a state, all date parts except the year, ages over 89, phone numbers, email addresses, Social Security numbers, MRNs, account numbers, device IDs, URLs, IP addresses, biometrics, photos, and any other unique code. ZIP codes may keep their first three digits only where that area has more than 20,000 people.</p>

<div class="callout"><p><strong>Why it matters:</strong> this is why a de-identifier deletes "March 9" but keeps "daily." A date can identify someone. A dosing frequency cannot.</p></div>

<h2 id="baa">BAA</h2>
<p class="post-expansion">Business Associate Agreement, 2003</p>
<p><strong>What it is:</strong> the contract a hospital must have with any outside company that handles PHI on its behalf. It sets out what the vendor may do with the data and how it must protect it.</p>
<p><strong>Where it came from:</strong> the Privacy Rule required it from 2003, but for the first six years the vendor was only accountable to the hospital, under the contract. Regulators could not go after the vendor directly. The HITECH Act of 2009 changed that, and the 2013 Omnibus Rule extended it to subcontractors: your hosting provider and your AI supplier are covered too.</p>

__FIG_REACH__

<div class="callout"><p><strong>Why it matters:</strong> you are a business associate the moment you receive PHI, signed contract or not. Refusing to work without a signed BAA is good practice, but the liability exists either way.</p></div>

<h2 id="npi">NPI</h2>
<p class="post-expansion">National Provider Identifier, 2007</p>
<p><strong>What it is:</strong> a ten-digit number, one per clinician or healthcare organization, used on every standard transaction.</p>
<p><strong>Where it came from:</strong> HIPAA's claims-standardization section required national identifiers, because a standard claim is useless if every insurer identifies the same doctor with a different number. The NPI became mandatory in 2007.</p>

<div class="callout"><p><strong>Why it matters:</strong> NPIs are public and searchable in an open registry. MRNs are protected. Same kind of key, opposite privacy rules.</p></div>

<h2 id="hitech">HITECH</h2>
<p class="post-expansion">Health Information Technology for Economic and Clinical Health Act, 2009</p>
<p><strong>What it is:</strong> the law that paid hospitals to adopt electronic records and made vendors directly liable for breaches.</p>
<p><strong>Where it came from:</strong> by 2008, most US hospitals were still on paper. HITECH, passed inside the 2009 stimulus package, offered about $27 billion in Medicare and Medicaid payments to hospitals that adopted a certified EHR and could show they were using it. A 2017 study compared hospitals that qualified for the money with those that did not.</p>

__FIG_BARS__

<div class="callout"><p><strong>Why it matters:</strong> HITECH is why there is electronic data for your product to read. It is also the law that made you liable for what you read.</p></div>

<h2 id="fhir">FHIR</h2>
<p class="post-expansion">Fast Healthcare Interoperability Resources, 2011</p>
<p><strong>What it is:</strong> a web API standard for health records. A patient, a lab result, or a medication is a JSON object at a predictable URL, fetched over ordinary HTTP.</p>
<p><strong>Where it came from:</strong> HL7 version 3 had failed to ship after a decade. In 2011 HL7 asked for a fresh start, and Grahame Grieve, a programmer in Melbourne, wrote a proposal over one summer using plain web conventions. HL7 adopted it, renamed it FHIR (pronounced "fire"), and Grieve insisted it be open source.</p>

<figure class="post-fig">
  <div class="grid-2 post-compare">
    <div class="post-panel post-panel-code">
      <p class="post-panel-year">HL7 v2, 1987</p>
      <pre><code>MSH|^~\&amp;|LAB|HOSP|...|ADT^A01|
PID|1||000001^^^HOSP^MR||
DOE^JANE||19800312|F|||
PV1|1|I|WARD^12^1|||...</code></pre>
      <p class="small">pipes and carets, position is meaning</p>
    </div>
    <div class="post-panel post-panel-code">
      <p class="post-panel-year">FHIR, 2011</p>
      <pre><code>GET /Patient/000001

{ "resourceType": "Patient",
  "identifier": [{"value": "000001"}],
  "birthDate": "1980-03-12",
  "gender": "female" }</code></pre>
      <p class="small">a URL and a JSON object a web developer can read</p>
    </div>
  </div>
  <figcaption>The same patient as an HL7 v2 message and as a FHIR resource. Both contain the MRN, and both are PHI.</figcaption>
</figure>

<div class="callout"><p><strong>Why it matters:</strong> FHIR is how modern apps read and write to an EHR, and it is the format US interoperability rules now require.</p></div>

<h2 id="icd-10-cm">ICD-10-CM</h2>
<p class="post-expansion">ICD, tenth revision, Clinical Modification, 2015</p>
<p><strong>What it is:</strong> the current US diagnosis code set. "CM" means the US-specific version, which is far more detailed than the WHO base version.</p>
<p><strong>Where it came from:</strong> the WHO released ICD-10 in the 1990s. Australia and Canada moved in 1998 and 2000. The US kept ICD-9-CM for clinical use until October 1, 2015, after Congress delayed the switch several times.</p>

<div class="callout"><p><strong>Why it matters:</strong> any US data from before late 2015 uses ICD-9 codes. Mixed datasets need a mapping.</p></div>

<h2 id="quick-reference">Quick reference</h2>
<dl class="post-quickref">
  <div><dt>ICD</dt><dd>Diagnosis codes. WHO standard; US uses ICD-10-CM since 2015.</dd></div>
  <div><dt>MRN</dt><dd>Hospital's patient ID. Protected; removed when de-identifying.</dd></div>
  <div><dt>CPT</dt><dd>Procedure codes. AMA, 1966.</dd></div>
  <div><dt>SOAP</dt><dd>Note structure: Subjective, Objective, Assessment, Plan.</dd></div>
  <div><dt>EMR / EHR</dt><dd>The digital chart. Terms are interchangeable in practice.</dd></div>
  <div><dt>HL7</dt><dd>Hospital messaging standard. Version 2 is everywhere.</dd></div>
  <div><dt>HIPAA</dt><dd>The 1996 law. Privacy Rule 2003, Security Rule 2005. No certification exists.</dd></div>
  <div><dt>PHI / ePHI</dt><dd>Identifiable health information. What the rules protect.</dd></div>
  <div><dt>Safe Harbor</dt><dd>Remove 18 identifier types and data is no longer PHI.</dd></div>
  <div><dt>BAA</dt><dd>Required vendor contract. Vendors directly liable since 2009, subcontractors since 2013.</dd></div>
  <div><dt>NPI</dt><dd>Public ten-digit provider ID, mandatory since 2007.</dd></div>
  <div><dt>HITECH</dt><dd>2009 law that funded EHR adoption and extended liability to vendors.</dd></div>
  <div><dt>FHIR</dt><dd>Web API standard for health records. Open source, 2011.</dd></div>
  <div><dt>ICD-10-CM</dt><dd>Current US diagnosis codes. Pre-2015 data uses ICD-9-CM.</dd></div>
</dl>

<h2 id="sources">Sources</h2>
<ol class="post-sources">
  <li>WHO, "History of the development of the ICD"; AAPC, "The Rules Are Changing: ICD's Continued Evolution" (2023).</li>
  <li>Mayo Clinic Proceedings, "Patient Records at Mayo Clinic: Lessons Learned From the First 100 Patients" (2008); Mayo Clinic History &amp; Heritage on Henry Plummer.</li>
  <li>Weed, "Medical Records That Guide and Teach," New England Journal of Medicine (1968); Elation Health and Patagonia Health histories of the EHR.</li>
  <li>Wikipedia, "HL7 International"; HL7, "FHIR Celebrates 10th Birthday"; Medblocks, "A History of HL7."</li>
  <li>HHS, "Summary of the HIPAA Privacy Rule"; HIPAA Journal, "The Comprehensive History of HIPAA" and "HIPAA Compliance for Business Associates."</li>
  <li>Barth-Jones et al., "Re-Identification Risk in HIPAA De-Identified Datasets" (2018); Harvard Gazette, "You're not so anonymous" (2011).</li>
  <li>Vedder Price and Crowell &amp; Moring alerts on the 2013 HIPAA Omnibus Final Rule.</li>
  <li>Adler-Milstein and Jha, "HITECH Act Drove Large Gains in Hospital Electronic Health Record Adoption," Health Affairs (2017).</li>
</ol>

<p class="post-backlink"><a href="/blog.html">&larr; All posts</a></p>

</div></section>
</article>

<div class="cta-band"><div class="wrap" style="padding-top:40px;padding-bottom:40px">
  <h2>Working with records that use every one of these terms?</h2>
  <div class="actions"><a class="btn btn-primary" href="/contact.html">Request a demo</a><a class="btn btn-ghost" href="/product.html">See how it works</a></div>
</div></div>
"""

ARTICLE = (ARTICLE
           .replace("__PDF_SIZE__", PDF_SIZE)
           .replace("__FIG_TIMELINE__", FIG_TIMELINE)
           .replace("__FIG_HIPAA__", FIG_HIPAA)
           .replace("__FIG_REACH__", FIG_REACH)
           .replace("__FIG_BARS__", FIG_BARS))


def _word_count(html: str) -> int:
    """Prose words only: code samples and drawings are not article text."""
    text = re.sub(r"<(svg|pre)\b.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return len(re.findall(r"[A-Za-z0-9][\w'-]*", text))


POSTS = [
    {
        "slug": "medical-record-acronyms",
        "path": "blog/medical-record-acronyms.html",
        "title": "Medical record acronyms: what each one means and why it exists",
        "page_title": "Medical record acronyms: what each one means and why it exists — Arbiter AI",
        "description": ("Fourteen terms you will meet in any healthcare product — ICD, MRN, CPT, "
                        "SOAP, EHR, HL7, HIPAA, PHI, Safe Harbor, BAA, NPI, HITECH, FHIR, "
                        "ICD-10-CM. What each is, where it came from, and why it matters."),
        "summary": ("ICD, MRN, CPT, SOAP, EHR, HL7, HIPAA, PHI, Safe Harbor, BAA, NPI, HITECH, "
                    "FHIR, ICD-10-CM. A field guide to the fourteen acronyms that shape every "
                    "healthcare integration, in the order they were invented."),
        "date": "2026-09-03",
        "date_human": "September 3, 2026",
        "reading_time": "10 min read",
        "section": "Healthcare data",
        "body": ARTICLE,
        "word_count": _word_count(ARTICLE),
    },
]

BLOG_INDEX_PATH = "blog.html"
BLOG_TITLE = "Blog — Arbiter AI"
BLOG_DESC = ("Field notes on clinical documents, health data standards, and building AI "
             "that a compliance officer can audit.")

# ---------------------------------------------------------------------- crawler surface
# __SITE__ is replaced with the canonical origin at build time.
_PUBLISHER = {"@type": "Organization", "name": "Arbiter AI", "url": "__SITE__",
              "logo": {"@type": "ImageObject", "url": "__SITE__/assets/logo.svg"}}


def _ld(obj):
    return ('<script type="application/ld+json">'
            + json.dumps(obj, separators=(",", ":")) + "</script>")


def _post_head(post):
    url = f"__SITE__/{post['path']}"
    blogposting = {
        "@context": "https://schema.org", "@type": "BlogPosting",
        "headline": post["title"], "description": post["description"],
        "datePublished": post["date"], "dateModified": post["date"],
        "author": {"@type": "Organization", "name": "Arbiter AI", "url": "__SITE__"},
        "publisher": _PUBLISHER,
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "image": "__SITE__/assets/og-image.png",
        "url": url, "wordCount": post["word_count"],
        "articleSection": post["section"], "inLanguage": "en-US",
    }
    breadcrumbs = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": "__SITE__/"},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": "__SITE__/blog.html"},
            {"@type": "ListItem", "position": 3, "name": post["title"], "item": url},
        ],
    }
    return ("".join([
        f'<meta property="article:published_time" content="{post["date"]}">',
        f'<meta property="article:modified_time" content="{post["date"]}">',
        f'<meta property="article:section" content="{post["section"]}">',
        '<meta property="article:publisher" content="__SITE__">',
        _ld(blogposting), _ld(breadcrumbs),
    ]))


def _blog_head():
    blog = {
        "@context": "https://schema.org", "@type": "Blog",
        "name": "The Arbiter AI blog", "url": "__SITE__/blog.html",
        "description": BLOG_DESC, "publisher": _PUBLISHER, "inLanguage": "en-US",
        "blogPost": [{"@type": "BlogPosting", "headline": p["title"],
                      "description": p["description"], "datePublished": p["date"],
                      "url": f"__SITE__/{p['path']}"} for p in POSTS],
    }
    return _ld(blog)


# --------------------------------------------------------------------------- index page

def _card(post):
    return (
        '<article class="blog-card">'
        f'<p class="blog-card-meta"><time datetime="{post["date"]}">{post["date_human"]}</time>'
        f'<span aria-hidden="true">&middot;</span>{post["reading_time"]}'
        f'<span aria-hidden="true">&middot;</span>{post["section"]}</p>'
        f'<h2><a href="/{post["path"]}">{post["title"]}</a></h2>'
        f'<p class="blog-card-summary">{post["summary"]}</p>'
        f'<p><a class="btn btn-ghost" href="/{post["path"]}">Read the article</a></p>'
        '</article>')


BLOG_INDEX = f"""
<section class="hero" style="padding-bottom:40px">
  <div class="wrap">
    <p class="kicker">Blog</p>
    <h1 style="max-width:16ch">Field notes from the edges of clinical data.</h1>
    <p class="lede">{BLOG_DESC} Written for the engineers and compliance teams who have to make both work at once.</p>
  </div>
</section>

<section class="section-tight"><div class="wrap">
  <div class="blog-list">{"".join(_card(p) for p in POSTS)}</div>
  <p class="small blog-feed">More is on the way. Subscribe by <a href="/feed.xml">RSS</a>, or <a href="/contact.html">tell us what you want written about</a>.</p>
</div></section>
"""

BLOG_PAGES = [
    (BLOG_INDEX_PATH, BLOG_TITLE, BLOG_DESC, BLOG_INDEX, {"head": _blog_head()}),
] + [
    (p["path"], p["page_title"], p["description"], p["body"],
     {"og_type": "article", "lastmod": p["date"], "head": _post_head(p)})
    for p in POSTS
]
