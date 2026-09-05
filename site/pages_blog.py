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

from build import REPO, gh, src

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
  <div class="actions"><a class="btn btn-primary" href="/how-it-works.html">Read the architecture</a><a class="btn btn-ghost" href="/security.html">Security model</a></div>
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

# ------------------------------------------------------------- engineering post-mortems
# Four write-ups from the first eval runs on the synthetic corpus. Every number is from
# CHANGELOG.md and the run outputs in platform/data/eval/; every code reference is a path
# in platform/. Bodies are plain HTML like the article above.

_CLOSING = """
<div class="cta-band"><div class="wrap" style="padding-top:40px;padding-bottom:40px">
  <h2>Where these checks live in the pipeline</h2>
  <div class="actions"><a class="btn btn-primary" href="/how-it-works.html">Read the architecture</a><a class="btn btn-ghost" href="/security.html">Security model</a></div>
</div></div>
"""


def _post_html(title: str, lede: str, date: str, date_human: str, reading_time: str,
               byline: str, body: str) -> str:
    return f"""
<article>
<section class="hero" style="padding-bottom:40px">
  <div class="wrap">
    <p class="kicker">Blog &middot; Engineering post-mortem</p>
    <h1 style="max-width:26ch">{title}</h1>
    <p class="lede">{lede}</p>
    <p class="post-meta"><time datetime="{date}">{date_human}</time><span aria-hidden="true">&middot;</span>{reading_time}<span aria-hidden="true">&middot;</span>{byline}</p>
    <p class="small">The code and tests referenced below are in the repository: <a href="{REPO}">github.com/yoonbo1/arbiterai</a>.</p>
  </div>
</section>

<section class="section-tight"><div class="wrap prose post-body">
{body}
<p class="post-backlink"><a href="/blog.html">&larr; All posts</a></p>
</div></section>
</article>
""" + _CLOSING


def _reading_time(html: str) -> str:
    return f"{max(1, round(_word_count(html) / 200))} min read"


# Post bodies are raw strings (regexes, SQL and JSON in them), so file paths are linked in a
# pass over the finished HTML rather than inline. Only an exact <code>path</code> span whose
# path is listed here becomes a link; function names, regexes, SQL, table and role names
# stay plain code, and nothing inside a <pre> block is touched.
_LINKED = {f: src(f) for f in (
    "eval/run_eval.py", "worker/deid.py", "worker/recognizers/address.py", "worker/recognizers/date_filter.py", "worker/recognizers/mrn.py", "worker/llm.py", "worker/graph.py",
    "worker/store.py", "gateway/main.py", "db/init.sql", "db/02_app_role.sh",
    "tests/test_deid.py")}
_LINKED["init.sql"] = src("db/init.sql", "init.sql")
_LINKED["02_app_role.sh"] = src("db/02_app_role.sh", "02_app_role.sh")
_LINKED["TODO.md"] = gh("TODO.md")


def _link_paths(html: str) -> str:
    return re.sub(r"<code>([^<]+)</code>",
                  lambda m: _LINKED.get(m.group(1), m.group(0)), html)


POST_DAILY = r"""
<h2 id="the-number">The number</h2>
<p>The first run of the eval harness (<code>eval/run_eval.py</code>) ingested 20 synthetic discharge summaries and asked 40 gold questions, two per patient. Answer accuracy came back at 0.575: 23 of 40. I expected the weak point to be retrieval or the 7B model. It was neither.</p>
<p>Grouping the 17 misses by question, 12 were "List the discharge medications." In 11 of those 12 the model had listed every drug with the right dose and left out the frequency. The answer was faithful to the chunk; the chunk was wrong. A stored chunk read:</p>
<pre><code>Medications: sertraline 50 mg &lt;DATE_TIME_2&gt;; atorvastatin 40 mg &lt;DATE_TIME_3&gt;</code></pre>
<p>The de-identifier had replaced "daily" and "nightly" with date tokens. Presidio's <code>DATE_TIME</code> recognizer inherits spaCy's <code>DATE</code> label, and spaCy's <code>DATE</code> covers durations and frequencies as well as calendar dates. Across the synthetic corpus, "daily" was scrubbed in 15 of the 19 documents that contained it and "nightly" in 4 of 8. The system prompt tells the model to keep placeholders exactly as written and to answer only from the excerpts, so it wrote "sertraline 50 mg" and stopped. It did what I asked.</p>
<p>The count that gave it away was <code>phi_tokens</code> grouped by entity type before the fix: DATE_TIME 84, PERSON 66, PHONE_NUMBER 20, MRN 20, LOCATION 18. Twenty synthetic documents with a date of birth, an admission date and a discharge date each is 60 date tokens. Eighty-four meant about two dozen were something else.</p>

<h2 id="the-fix">The fix</h2>
<p>Safe Harbor removes dates tied to a person: birth, admission, discharge, death. A dosing frequency or a follow-up interval is clinical content, and there is no re-identification risk in the word "nightly". In <code>worker/recognizers/date_filter.py</code> (the filter lived in <code>worker/deid.py</code> when this was found) a DATE_TIME hit is now kept only if it contains something calendar-like:</p>
<pre><code>_DATE_LIKE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\b"  # month names
    r"|\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b"                                  # 3/5/2024, 03-05-24
    r"|\b\d{4}-\d{2}-\d{2}\b"                                                  # ISO
    r"|\b(?:19|20)\d{2}\b"                                                      # a year
    r"|\b\d{1,2}(?:st|nd|rd|th)\b",                                             # 5th (of March)
    re.IGNORECASE)


def _is_identifying_date(span: str) -> bool:
    return bool(_DATE_LIKE.search(span))</code></pre>
<p><code>Scrubber.__call__</code> applies it as a filter on the analyzer's results before anything is replaced. "daily", "nightly" and "in 2 weeks" survive; "March 9", "03/05/2024" and "1985-03-12" do not. Two tests pin both directions: <code>test_dosing_frequency_and_duration_are_not_redacted</code> and <code>test_calendar_dates_are_still_redacted</code> in <code>tests/test_deid.py</code>.</p>
<p>The filter also uncovered something it had been masking. A bare ten-digit number after <code>Tel:</code> had only been caught because spaCy mislabelled it as a date; with the filter in place it would have survived. The phone recognizer gained a bare-NANP pattern that scores 0.35 on its own, below the 0.5 threshold, and clears it only when Presidio's context enhancer finds a phone-like word nearby. Removing a false positive can expose a false negative that was hiding behind it. Re-run recall after every relaxation.</p>

<h2 id="three-more-gaps">Three more stock-recognizer gaps from the same pass</h2>
<p>Running the de-identifier against the real Presidio engine in <code>tests/test_deid.py</code> and then against the synthetic corpus found three more places where the stock recognizers fall short of a clinical chart.</p>
<ul>
<li><strong>MRNs were never scrubbed.</strong> The custom MRN pattern scored 0.4 against a 0.5 threshold, so every hit was discarded before it reached the resolver and the first test summary came back with its MRN intact. <code>_mrn_recognizer()</code> was rewritten: a labelled <code>MRN: 1234567</code> now scores 0.85 and only the digits are replaced, so the model still sees <code>MRN: &lt;MRN_1&gt;</code>. <code>test_labeled_mrn_forms</code> covers six spellings of the label. That rewrite is why the table above shows exactly 20 MRN tokens for 20 documents.</li>
<li><strong>Phone numbers with extensions.</strong> Presidio's phonenumbers-based recognizer missed NANP numbers with extensions such as <code>+1-921-899-3518x19093</code>. <code>_phone_recognizer()</code> is a regex backstop: optional country code, area code with or without parentheses, and an extension group <code>(?:\s*(?:x|ext\.?|extension)\s*\d{1,6})?</code>. <code>test_phone_forms_with_extensions</code> covers five formats.</li>
<li><strong>Physician surnames that are common words.</strong> spaCy missed Dr. Fields, Dr. Lewis, Dr. Young and Dr. Holder: the four whole-string survivors in run 1, which is where the synthetic de-id recall of 0.967 (116/120) came from. <code>_name_recognizer()</code> anchors on a title or field label (<code>Dr.</code>, <code>Doctor</code>, <code>Attending:</code>, <code>Patient:</code>, <code>Name:</code>) and replaces only the name, so <code>Attending: Dr. &lt;PERSON_2&gt;</code> keeps its title. Presidio compiles every pattern with <code>IGNORECASE</code>, so the name part is wrapped in <code>(?-i:...)</code> to stop at the first lowercase word; without that, "Dr. Priya Raghunathan-Okafor reviewed" swallowed "reviewed".</li>
</ul>
<p>A later finding in the same family: after those fixes some charts read <code>Attending: &lt;PERSON_2&gt;. &lt;PERSON_1&gt;</code>. spaCy had tagged the bare title "Dr" as a person, and the model answered "the attending physician is Dr." <code>_trim_person()</code> now drops a span whose every word is a title or a field label, trims leading titles and trailing labels off the rest ("Dr Young" becomes "Young", "Joshua Duncan DOB" becomes "Joshua Duncan"), and drops the span if nothing is left. Tests: <code>test_bare_title_is_never_a_person_token</code> and <code>test_person_span_is_trimmed_of_leading_title_and_trailing_label</code>.</p>

<h2 id="before-and-after">Before and after</h2>
<div class="tbl-wrap"><table>
<thead><tr><th>Synthetic corpus, 20 documents, 40 questions</th><th>Run 1</th><th>Run 4</th></tr></thead>
<tbody>
<tr><td>Answer accuracy, strict</td><td>0.575 (23/40)</td><td>0.95 (38/40)</td></tr>
<tr><td>Misses on "List the discharge medications"</td><td>12 of 17 misses; 11 caused by a scrubbed frequency</td><td>the two misses left in the run are Tesseract misreads</td></tr>
<tr><td>"daily" scrubbed</td><td>15 of 19 documents</td><td>kept; pinned by test</td></tr>
<tr><td>"nightly" scrubbed</td><td>4 of 8 documents</td><td>kept; pinned by test</td></tr>
<tr><td>De-id recall, whole string</td><td>0.967 (116/120)</td><td>1.000</td></tr>
<tr><td>Labelled MRN score vs. 0.5 threshold</td><td>0.4, never fired</td><td>0.85, digits only replaced</td></tr>
</tbody></table></div>
<p>The two remaining misses are Tesseract misreads on the synthetic scans that the model copied faithfully: "fisinopril" for lisinopril and "HbAtc" for HbA1c. Those need the vision route on a GPU box or a drug-name correction step, and they are tracked in <code>TODO.md</code>.</p>
<div class="callout"><p><strong>Scope.</strong> Every number here is from the synthetic corpus: Faker names, one document type, dates in three formats. It says nothing about recall on real names or real scans. The i2b2 2014 de-identification set is the real test, pending credentialed access. The recall side of this run has its own post: <a href="/blog/deid-recall-flattering-metric.html">the whole-string recall metric was flattering</a>.</p></div>

<h2 id="what-to-check">What to check in your own pipeline</h2>
<ul>
<li>Count tokens by entity type, not just recall. 84 DATE_TIME tokens on 20 documents with three dates each was the tell.</li>
<li>Diff one scrubbed document against its source and read the medication list by hand.</li>
<li>Check that your date recognizer separates calendar dates from frequencies and durations. spaCy's <code>DATE</code> label does not.</li>
<li>Assert in a test that every custom recognizer's score clears the threshold. A 0.4 pattern against a 0.5 gate is silently doing nothing.</li>
<li>Scrub "Attending: Dr." on its own and check that no PERSON token comes out.</li>
<li>After removing any false positive, re-run recall. Something may have been depending on it.</li>
</ul>
<p>The validation side of the same run, where the judge threw away correct answers, is in <a href="/blog/7b-judge-citation-placement.html">the 7B judge scored identical facts 0.0 or 1.0</a>. Where de-identification sits relative to the model call is on the <a href="/how-it-works.html">architecture page</a>.</p>
"""

POST_RECALL = r"""
<h2 id="the-number">The number</h2>
<p>The harness in <code>eval/run_eval.py</code> is simple on purpose. The synthetic generator records every identifier it injects into each of 20 discharge summaries: name, date of birth, MRN, phone, address, attending physician. After ingest, the harness reads every stored chunk as the application role and checks whether each injected string appears verbatim. Run 1 reported a synthetic de-id recall of 0.967: 116 of 120 strings gone. The four survivors were all <code>Dr. &lt;common-word surname&gt;</code>, which spaCy's NER had missed and which a title-anchored recognizer fixed (that story is in <a href="/blog/spacy-redacted-daily.html">the "daily" post</a>).</p>
<p>That read as a near miss on the 0.99 gate. It was not. A stored chunk read:</p>
<pre><code>Address: 1049 Mitchell Lights Suite 075, &lt;LOCATION_1&gt;, AR 29101</code></pre>
<p>The injected identifier was the whole 40-character string, street through ZIP. The check asked whether that string appeared in the chunks. It did not, because the city was gone, so the metric counted the address as removed. The street number, street name, unit, state and ZIP were all sitting in the index.</p>
<p>Counting by component across the 20 synthetic documents: the ZIP survived in 14 of 20, the street line in 7 of 20, the city in 6 of 20, and the state in 20 of 20 (a state is allowed under Safe Harbor). By component, roughly 97 of 120 identifiers were actually gone: about 0.81, not 0.967.</p>
<p>The city was the only part being caught because Presidio ships no US street-address recognizer. spaCy's NER tags a city it recognizes, and nothing else on the line. The Faker-invented cities in the synthetic corpus (Blankenshipstad, Hernandezview, Kingland, New Amber) it mostly did not recognize either.</p>

<h2 id="fix-1">Fix 1: a metric that partial hits cannot flatter</h2>
<p><code>deid_recall_strict</code> in <code>eval/run_eval.py</code> splits each multi-part identifier on commas and counts any surviving component of four or more characters as a leak. It is reported alongside the old number, not instead of it, so the gap between the two is itself visible in every run.</p>
<pre><code>parts = [(p, part.strip()) for p in phi for part in p.split(",") if len(part.strip()) &gt;= 4]
leaked_parts = sorted({part for _, part in parts if part in text})
...
"deid_recall_strict": 1 - len(leaked_parts) / max(1, len({part for _, part in parts})),
"phi_component_survivors": leaked_parts[:8],</code></pre>

<h2 id="fix-2">Fix 2: an address recognizer</h2>
<p>The address recognizer (now its own module, <code>worker/recognizers/address.py</code>; it lived in <code>worker/deid.py</code> when this was found) adds four LOCATION patterns:</p>
<ul>
<li>A labelled <code>Address:</code> line, taken whole as <code>street, city, ST ZIP</code> (up to three comma segments) and stopping at a run of two spaces, the next <code>Label:</code> on the line, or end of line. Score 0.85.</li>
<li>A street line: a number, one to four words, a USPS suffix (Street, Lights, Roads, and the rest of the list), an optional unit. Score 0.6.</li>
<li><code>City, ST 12345</code>, which needs no knowledge of city names at all. Score 0.6. This is the pattern that closed the Faker-city gap.</li>
<li>A bare ZIP, <code>\d{5}(?:-\d{4})?</code>, at 0.35, below the 0.5 threshold, lifted only when address context words (address, street, zip, apt, suite) are nearby. It started at 0.6, and <code>WBC 11000</code> was scrubbed as a ZIP code.</li>
</ul>
<p>Tests: <code>test_labelled_address_line_is_fully_redacted</code> and <code>test_city_state_zip_without_label_is_redacted</code>.</p>

<h2 id="fix-3">Fix 3: overlapping spans merge into their union</h2>
<p>With the city pattern in place a new failure appeared. In <code>Kingland, TX 75001</code>, spaCy tagged <code>Kingland</code> as LOCATION at 0.85 and my pattern tagged the whole <code>Kingland, TX 75001</code> at 0.6. Presidio dropped the ZIP as a duplicate contained in the longer span, and the old <code>_select()</code> rule, "keep the best-scoring overlapping span, drop the rest", kept the shorter, higher-scoring city. The index read <code>&lt;LOCATION_3&gt;, TX 75001</code>.</p>
<p><code>_select()</code> now merges overlapping candidates into their union, typed by the highest-scoring member:</p>
<pre><code>for r in sorted((r for r in results if r.end &gt; r.start), key=lambda r: (r.start, -(r.end - r.start))):
    if groups and r.start &lt; groups[-1]["end"]:
        g = groups[-1]
        g["end"] = max(g["end"], r.end)          # the union, never the best fragment
        ...</code></pre>
<p>The argument for union is that the two error types are not symmetric. Over-redaction is recoverable: the token maps back through <code>phi_tokens</code> and re-identification restores it for the authorized caller after validation (<a href="/how-it-works.html">how it works</a>). Under-redaction is a breach. So no fragment of any above-threshold candidate may survive, and union is the only safe policy. <code>test_select_merges_overlaps_into_their_union_typed_by_the_best_member</code> covers a phone number with an MRN-shaped run inside it, a year inside a full date, and a city inside a <code>City, ST ZIP</code> line.</p>

<h2 id="harness">The harness shape, and four iterations in a day</h2>
<p>20 synthetic records, two gold questions each, 40 queries. One run ingests 20 documents, asks 40 questions, and reads the chunks: about 2 min 50 s of wall time and about half a cent at the placeholder per-token rates in <code>worker/llm.py</code>. That is cheap enough to run after every change, which is how the four iterations fit into one day.</p>
<div class="tbl-wrap"><table>
<thead><tr><th>Run (synthetic, 20 docs)</th><th>Whole-string recall</th><th>Strict per-component</th><th>What changed before it</th></tr></thead>
<tbody>
<tr><td>1</td><td>0.967</td><td>not measured; about 0.81 by hand</td><td>baseline</td></tr>
<tr><td>2</td><td>1.000</td><td>0.9625</td><td>title-anchored names; labelled <code>Address:</code>, street-line and ZIP patterns; the strict metric</td></tr>
<tr><td>3</td><td>1.000</td><td>1.000</td><td><code>City, ST 12345</code> pattern; labelled pattern takes the whole line</td></tr>
<tr><td>4</td><td>1.000</td><td>1.000</td><td>union overlap resolution, whitespace trim, case-sensitive names (from new tests, not the eval)</td></tr>
</tbody></table></div>
<p>The six strict survivors in run 2 were all Faker city names: Blankenshipstad, Hernandezview, Kingland, New Amber, New Brendaton, New Bryanhaven. Run 3's <code>City, ST 12345</code> pattern removed them without knowing any of them.</p>
<div class="callout"><p><strong>What 1.000 does not prove.</strong> On the regenerated synthetic corpus that includes OCR'd scans, whole-string recall was 0.992 when this was written: one MRN survived because Tesseract read its <code>MRN:</code> label as <code>MAN:</code>, and the recognizer was anchored on the exact label. (Update, 2026-09-05: <code>worker/recognizers/mrn.py</code> now accepts one OCR error in the label and a bare 6-to-10-digit run on a demographics line; the same corpus scores 1.000 whole-string and strict.) Beyond that, the synthetic number says nothing about real names (Faker names are clean and capitalized), about OCR-mangled identifiers in general, or about facility names, which are not scrubbed at all. Those are in <code>TODO.md</code>. The i2b2 2014 de-identification corpus is the real test, pending credentialed access.</p></div>

<h2 id="what-to-check">What to check in your own pipeline</h2>
<ul>
<li>If an identifier has parts, score the parts. A whole-string check passes when one word of an address is gone.</li>
<li>Read a stored chunk. One <code>SELECT text FROM chunks LIMIT 1</code> found this; the metric never would have.</li>
<li>Do not rely on NER for geography. Add patterns for <code>City, ST ZIP</code> and street lines that need no city list.</li>
<li>Resolve overlapping spans as a union. "Best span wins" leaves the rest of the line in the index.</li>
<li>Run the leak check as the role RLS applies to. If the harness connects as the owner, it reads every tenant's chunks and proves nothing about isolation (<a href="/blog/postgres-superuser-bypasses-rls.html">the superuser post</a>).</li>
<li>Make one iteration cheap enough to run four times a day, and report the new metric next to the old one.</li>
</ul>
<p>What the de-identifier guarantees, and what it does not, is written up on the <a href="/security.html">security model</a> page.</p>
"""

POST_JUDGE = r"""
<h2 id="the-number">The number</h2>
<p>The validation node in <code>worker/graph.py</code> runs three checks on every answer before it can be re-identified: no PHI in the output (<code>deid.contains_phi</code>), at least one citation to a retrieved chunk, and a grounding score. The grounding score comes from <code>llm.faithfulness_score</code>, which asks the small model (qwen2.5:7b-instruct via Ollama, temperature 0) for a single number between 0 and 1, the fraction of the answer's claims that the excerpts support, and gates at 0.7 or above.</p>
<p>In run 1 on the synthetic corpus, validation rejected 5 of 40 answers. All five were the same question, "What is the patient's most recent HbA1c?", and all five were correct. A typical one: "The patient's most recent HbA1c is 9.0% [7]."</p>
<p>I re-issued the exact judge prompts by hand, changing only the answer text:</p>
<pre><code>The patient's most recent HbA1c is 9.0% [7].   -&gt;  0.0
The patient's most recent HbA1c is 9.0%. [7]   -&gt;  1.0
The patient's most recent HbA1c is 9.0%.       -&gt;  1.0
HbA1c 9.0% [7]                                 -&gt;  1.0</code></pre>
<p>Same facts, same context, same model, temperature 0. A citation marker before the full stop scored 0.0; after it, 1.0. The judge prompt already told the model to ignore citation markers like <code>[12]</code>. It did not.</p>

<h2 id="escalation">Escalation made it worse, at about 8x the cost</h2>
<p><code>after_validate</code> in <code>worker/graph.py</code> sends a rejected answer back to <code>generate</code> once, on the "large" tier, before failing the job. On this machine there is no separate large model: <code>LARGE_MODEL_URL</code> is unset and <code>worker/llm.py</code> falls back to the small tier's URL and model. So escalation re-ran the same model at temperature 0, got the same "9.0% [7].", got the same 0.0 from the same judge, and discarded a correct answer for the second time.</p>
<p>The cost accounting made it look expensive rather than free, because the escalated call is metered at the large-tier rate: 0.0539 cents against 0.0066 cents for the small-tier attempt, at the placeholder rates in <code>COST_PER_1K</code>. About 8x, to reproduce a rejection.</p>

<h2 id="unbilled">Half the model traffic was never counted</h2>
<p>While reading the judge's prompts I noticed their size: about 330 prompt tokens per call, the judge instructions plus every retrieved chunk plus the answer. The judge runs on every answer, and the answer call is roughly the same size, so the judge was about half of all small-tier traffic. <code>faithfulness_score</code> returned only the float and discarded the response's <code>usage</code>. None of it reached <code>jobs.tokens_small</code>, so the per-query cost in the eval report was about half the truth.</p>

<h2 id="the-fix">The fix</h2>
<p>Both changes are in <code>worker/llm.py</code>. Citation markers are stripped before the answer reaches the judge, and the judge returns its token count so <code>graph.validate</code> can meter it:</p>
<pre><code>_CITE = re.compile(r"\s*\[\d+\]")


def faithfulness_score(answer_text: str, chunks: list[dict]) -&gt; tuple[float, int]:
    ctx = "\n".join(c["text"] for c in chunks)
    claim = _CITE.sub("", answer_text).strip()
    out, used = _chat("small", [
        {"role": "system", "content": JUDGE},
        {"role": "user", "content": f"CONTEXT:\n{ctx}\n\nANSWER:\n{claim}"}], max_tokens=8)
    ...
    return max(0.0, min(1.0, v)), used</code></pre>
<pre><code># worker/graph.py, validate()
score, used = llm.faithfulness_score(state["answer_deid"], state["chunks"])
usage["small"] = usage.get("small", 0) + used      # judge calls are metered too</code></pre>
<p>The judge prompt itself had already been rewritten once during bring-up: a vaguer "fraction of claims" wording scored a fully supported answer 0.5 on this model, below the gate. The current <code>JUDGE</code> text asks for 1.0 if every claim is stated in the context, 0.0 if none is, otherwise the fraction, and was measured at 1.0 supported and 0.0 unsupported. The lesson from the citation bug is that an instruction to ignore something is not the same as removing it. Normalize the input; do not ask a 7B model to.</p>

<h2 id="before-and-after">Before and after</h2>
<div class="tbl-wrap"><table>
<thead><tr><th>Synthetic corpus, 40 queries</th><th>Run 1</th><th>Run 2</th></tr></thead>
<tbody>
<tr><td>Answers rejected by validation</td><td>5</td><td>1</td></tr>
<tr><td>Escalations</td><td>5</td><td>1</td></tr>
<tr><td>Answer accuracy, strict</td><td>0.575</td><td>0.95</td></tr>
<tr><td>Small-tier tokens for the run</td><td>13,055 (judge unbilled)</td><td>24,969 (judge metered)</td></tr>
<tr><td>Large-tier tokens for the run</td><td>1,586</td><td>297</td></tr>
<tr><td>Cost per query, placeholder rates</td><td>0.012 cents</td><td>0.014 cents</td></tr>
</tbody></table></div>
<p>The small-tier count roughly doubling is the honest number, not a regression: nothing changed in the answer path, the judge's calls are simply counted now. Runs 3 and 4 came in at about 24,000. The one rejection that remained in run 2 was an answer that copied a Tesseract misread, "HbAtc 7.2%", verbatim from a scanned page; that is an OCR problem, tracked separately. On the regenerated synthetic corpus the QA eval reports 0 validation failures and accuracy 0.95.</p>
<div class="callout"><p><strong>Still open</strong> (both in <code>TODO.md</code>). Escalating to the same model at temperature 0 cannot change a verdict, so either the large tier gets a genuinely larger model or escalation is skipped when the tiers are identical. And a 7B model asked for one number is format-sensitive by nature; stripping citations removed the case I found, not the class. Claim-level checking, or a calibrated entailment model with judge agreement measured on a labelled set, is the longer-term answer.</p></div>

<h2 id="what-to-check">What to check in your own pipeline</h2>
<ul>
<li>Log the judge's verdict next to the answer for every rejection, and read the rejections. Five identical questions was the tell.</li>
<li>Reproduce with the exact prompt and change one thing. Citation placement took four calls to isolate.</li>
<li>Normalize the answer before judging: strip citations, placeholders and trailing punctuation. Do not rely on the prompt to do it.</li>
<li>Meter every model call, including the ones that return one number. A judge that runs on every answer is not overhead; it is half the bill.</li>
<li>Check what your "large" tier actually is. If it resolves to the same model, escalation is a retry at a higher price.</li>
<li>Compare the cost of a rejection to the cost of an answer. Here a wrong rejection cost more than a right answer.</li>
</ul>
<p>The other 12 misses in the same run were the de-identifier's fault, not the judge's: <a href="/blog/spacy-redacted-daily.html">spaCy redacted the word "daily"</a>. Where validation sits in the query graph, and what it gates, is on the <a href="/how-it-works.html">architecture page</a>.</p>
"""

POST_RLS = r"""
<h2 id="the-bug">The bug</h2>
<p><code>db/init.sql</code> did the right things on paper. Row-level security was enabled on <code>patients</code>, <code>documents</code>, <code>chunks</code>, <code>phi_tokens</code> and <code>jobs</code>, each with a <code>tenant_isolation</code> policy:</p>
<pre><code>CREATE POLICY tenant_isolation ON chunks
  USING      (tenant_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);</code></pre>
<p>It also created an <code>app_rw</code> role, with a hard-coded password, that nothing used. The gateway and the worker both connected with <code>DATABASE_URL</code> as the <code>hipaa</code> role: the database owner and, in the compose file, the superuser. Postgres exempts superusers from row-level security entirely, and a table's owner bypasses it too unless <code>FORCE ROW LEVEL SECURITY</code> is set. So all five policies were silently ignored. The README's claim that another tenant's jobs return 404 "via RLS" was false. The job lookup in <code>gateway/main.py</code> is <code>SELECT status, result, finished_at FROM jobs WHERE id=$1</code>, with no tenant filter at all, because the policy was meant to supply it. With the policy bypassed, any tenant's key could read any job by id.</p>
<p>Five tables under RLS, zero enforced against the role in use. I found it by asking what role the eval harness's leak check was running as. If the harness reads chunks as the owner, it reads every tenant's chunks, and a zero-leak result proves nothing about isolation.</p>

<h2 id="the-fix">The fix</h2>
<p><strong>Both services connect as <code>app_rw</code>.</strong> The role is created in <code>db/init.sql</code> without a password and cannot log in until <code>db/02_app_role.sh</code> sets one. The split is forced by the Postgres image: init <code>.sql</code> files get no environment substitution, init <code>.sh</code> files do. The password is passed as a psql variable, so it never appears in SQL text or in a log line:</p>
<pre><code>: "${PG_APP_PASSWORD:?PG_APP_PASSWORD must be set in the postgres service environment}"
psql -v ON_ERROR_STOP=1 -v pw="$PG_APP_PASSWORD" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" &lt;&lt;'SQL'
ALTER ROLE app_rw PASSWORD :'pw';
SQL</code></pre>
<p><strong>The grants were wrong too.</strong> The blanket <code>GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO app_rw</code> had given the application role UPDATE on <code>audit_log</code>. The <code>REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC</code> above it does not touch a direct grant, so append-only was defeated by the very next statement. The grants now read:</p>
<pre><code>GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT DELETE ON chunks, phi_tokens TO app_rw;        -- re-ingest replaces derived rows
REVOKE UPDATE, DELETE ON audit_log FROM app_rw;      -- append-only again
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_rw;
-- no CREATE on schema public: the app never creates tables</code></pre>
<p><strong>Tenant context is transaction-local.</strong> Every handler in <code>gateway/main.py</code> and <code>tenant_conn()</code> in <code>worker/store.py</code> set it with <code>set_config('app.tenant_id', $1, true)</code>. The <code>true</code> means "local to this transaction". With a session-level <code>SET</code>, a pooled connection returned after tenant A's request would carry A's context into whatever transaction borrowed it next.</p>
<p><strong>The harness refuses to lie.</strong> <code>eval/run_eval.py</code> checks its own role before it reads a single chunk:</p>
<pre><code>if con.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
    raise SystemExit("DATABASE_URL must use the RLS-bound app role (app_rw), not the owner/superuser")</code></pre>

<h2 id="probes">The probes</h2>
<p>Two tenants, A and B, each with its own API key, and one ingested document under A.</p>
<pre><code>GET /v1/jobs/{A's job}   Authorization: Bearer {key A}   -&gt;  200
GET /v1/jobs/{A's job}   Authorization: Bearer {key B}   -&gt;  404  {"detail":"job not found"}

-- psql as app_rw
SELECT count(*) FROM chunks;                                          -- app.tenant_id unset
 0
SELECT set_config('app.tenant_id', '&lt;A&gt;', true); SELECT count(*) FROM chunks WHERE tenant_id = '&lt;B&gt;';
 0                                                                    -- and A's rows are visible
SELECT set_config('app.tenant_id', '&lt;B&gt;', true); SELECT count(*) FROM chunks WHERE tenant_id = '&lt;A&gt;';
 0                                                                    -- the reverse
SELECT set_config('app.tenant_id', '&lt;A&gt;', true); INSERT INTO chunks (tenant_id, ...) VALUES ('&lt;B&gt;', ...);
 ERROR:  new row violates row-level security policy for table "chunks"
SELECT has_schema_privilege('app_rw', 'public', 'CREATE');
 f

-- psql as the owner, for contrast
SELECT count(*) FROM chunks;                                          -- every tenant's rows</code></pre>
<p>The owner session seeing everything is the before state. That is what the gateway and the worker had been running as.</p>

<h2 id="before-and-after">Before and after</h2>
<div class="tbl-wrap"><table>
<thead><tr><th></th><th>Before</th><th>After</th></tr></thead>
<tbody>
<tr><td>Role the services connect as</td><td><code>hipaa</code> (owner, superuser)</td><td><code>app_rw</code></td></tr>
<tr><td>Tables with a policy that is enforced</td><td>0 of 5</td><td>5 of 5</td></tr>
<tr><td>Key B on tenant A's job</td><td>200; the lookup has no tenant filter of its own</td><td>404 from the policy</td></tr>
<tr><td><code>app_rw</code> with no tenant context</td><td>not applicable</td><td>0 rows</td></tr>
<tr><td>INSERT for B while set to A</td><td>succeeds</td><td>rejected by the policy</td></tr>
<tr><td>UPDATE on <code>audit_log</code> for the app role</td><td>granted, by the blanket grant</td><td>revoked</td></tr>
<tr><td>Application password</td><td>hard-coded in <code>init.sql</code></td><td><code>PG_APP_PASSWORD</code>, via <code>02_app_role.sh</code></td></tr>
<tr><td>Eval harness as a superuser</td><td>ran; leak check meaningless</td><td>refuses to start</td></tr>
</tbody></table></div>

<h2 id="design">The design point</h2>
<p>Tenant isolation must not depend on application code being bug-free. A lookup with no tenant filter (which is exactly what the job endpoint is, by design), a wrong join, a connection that came back from the pool with someone else's context: with row-level security enforced, each of those returns zero rows or an error. Without it, each returns another tenant's records. But that guarantee is only real if the policy applies to the role the application actually uses. A policy the connecting role is exempt from is documentation, not a control, and it is worse than no policy because it is reassuring. The invariants this enforces, and how each is tested, are on the <a href="/security.html">security model</a> page.</p>
<div class="callout"><p><strong>Update, 2026-09-05.</strong> The gap this callout originally described is closed: <code>audit_log</code> now carries the same <code>tenant_isolation</code> policy as the PHI tables (migration <code>003_audit_log_rls.sql</code>), so an <code>app_rw</code> session set to tenant A sees none of tenant B's audit rows, and an insert for the wrong tenant violates the policy. The two admin events that had no tenant context (<code>key.created</code>, <code>key.revoked</code>) now run under the key's tenant. What remains true: the application role can still read every row of its own tenant, and nothing here substitutes for the KMS-issued keys, WORM storage and access review a deployment adds around it.</p></div>

<h2 id="what-to-check">What to check in your own pipeline</h2>
<ul>
<li>From inside the application's own connection: <code>SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user</code>. If either is true, your policies are not applying.</li>
<li>Check table ownership too. Owners bypass RLS unless <code>FORCE ROW LEVEL SECURITY</code> is set.</li>
<li>Run the negative probes as the application role: no context set, expect zero rows; an INSERT for the wrong tenant, expect an error.</li>
<li>Read every blanket <code>GRANT ... ON ALL TABLES</code> and check what it gave on the tables that are supposed to be append-only.</li>
<li>Set tenant context with <code>set_config(..., true)</code> or <code>SET LOCAL</code>, never a session-level <code>SET</code>, on any pooled connection.</li>
<li>Make the test harness refuse to run as a role that bypasses RLS, so a passing leak check means something.</li>
<li>List the tables that have no policy, and write that list down where the next person will read it.</li>
</ul>
<p>The leak check that this role change made meaningful is described in <a href="/blog/deid-recall-flattering-metric.html">the recall metric post</a>.</p>
"""

_NEW_POSTS = [
    {
        "slug": "spacy-redacted-daily",
        "title": "spaCy redacted the word 'daily' — and broke 11 of 12 medication lists",
        "description": ("Post-mortem: Presidio's stock date recognizer treated dosing frequencies as "
                        "identifiers and cut answer accuracy to 0.575 on a synthetic corpus. The "
                        "calendar-date filter, three more stock-recognizer gaps, and what to check."),
        "summary": ("The first eval run scored 23 of 40. Twelve misses were the same question, and "
                    "eleven of them traced to the de-identifier replacing 'daily' with a date token. "
                    "The fix, three more Presidio gaps, and the tokens-by-entity count that gave it away."),
        "lede": ("The first eval run scored 23 of 40 gold questions. Twelve misses were the same "
                 "question, and the de-identifier had caused eleven of them."),
        "body_src": POST_DAILY,
    },
    {
        "slug": "deid-recall-flattering-metric",
        "title": "Our de-id recall read 0.967 while ZIP codes survived in 14 of 20 documents",
        "description": ("Post-mortem: a whole-string recall metric passed addresses whose street "
                        "line and ZIP were still in the index. The per-component metric, an address "
                        "recognizer, union overlap resolution, and four eval iterations in a day."),
        "summary": ("The metric checked whether each injected identifier survived whole. An address "
                    "is four things and only the city was ever tokenized. A strict per-component "
                    "metric, an address recognizer, and why overlapping spans must merge into their union."),
        "lede": ("The metric checked whether each injected identifier survived whole. An address is "
                 "four things, and only one of them was ever tokenized."),
        "body_src": POST_RECALL,
    },
    {
        "slug": "7b-judge-citation-placement",
        "title": "The 7B judge scored identical facts 0.0 or 1.0 depending on where the citation sat",
        "description": ("Post-mortem: the grounding judge rejected five correct answers over citation "
                        "placement, escalation re-ran the same model at 8x the cost, and the judge's "
                        "calls were half of all model traffic and unbilled. The fix and the accounting."),
        "summary": ("Five correct answers rejected, all the same question. '9.0% [7].' scored 0.0 and "
                    "'9.0%. [7]' scored 1.0. Escalation re-ran the same model at 8x the cost, and the "
                    "judge's calls were half the traffic and never metered."),
        "lede": ("Five correct answers were rejected, all to the same question. The only difference "
                 "between a 0.0 and a 1.0 was which side of the full stop the citation sat on."),
        "body_src": POST_JUDGE,
    },
    {
        "slug": "postgres-superuser-bypasses-rls",
        "title": "The services were connecting as the Postgres superuser, which silently bypasses RLS",
        "description": ("Post-mortem: five tables had row-level security policies and none applied, "
                        "because the gateway and worker connected as the owner. The app role, the "
                        "grants, transaction-local tenant context, and the probes that prove it now."),
        "summary": ("Five tables carried a tenant-isolation policy and none of it applied, because "
                    "both services connected as the database owner. The app role, the audit_log grant "
                    "that defeated append-only, and the cross-tenant probes."),
        "lede": ("Five tables carried a tenant-isolation policy. None of it applied to the role the "
                 "services were using."),
        "body_src": POST_RLS,
    },
]

for _p in _NEW_POSTS:
    _body = _link_paths(_p["body_src"])
    _html = _post_html(_p["title"], _p["lede"], "2026-09-04", "September 4, 2026",
                       _reading_time(_body), "Yoonbo Cho", _body)
    POSTS.append({
        "slug": _p["slug"],
        "path": f"blog/{_p['slug']}.html",
        "title": _p["title"],
        "page_title": f"{_p['title']} — Arbiter AI",
        "description": _p["description"],
        "summary": _p["summary"],
        "date": "2026-09-04",
        "date_human": "September 4, 2026",
        "reading_time": _reading_time(_body),
        "section": "Engineering post-mortem",
        "author": "Yoonbo Cho",
        "body": _html,
        "word_count": _word_count(_body),
    })

# Newest first on the index and in the feed (stable sort keeps the four post-mortems in
# the order above, which is the order the home page links them).
POSTS.sort(key=lambda p: p["date"], reverse=True)

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
        "author": ({"@type": "Person", "name": post["author"],
                    "worksFor": {"@type": "Organization", "name": "Arbiter AI", "url": "__SITE__"}}
                   if post.get("author") else
                   {"@type": "Organization", "name": "Arbiter AI", "url": "__SITE__"}),
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
  <p class="small blog-feed">More is on the way. Subscribe by <a href="/feed.xml">RSS</a>, or <a href="/contact.html">tell me what you want written about</a>.</p>
</div></section>
"""

BLOG_PAGES = [
    (BLOG_INDEX_PATH, BLOG_TITLE, BLOG_DESC, BLOG_INDEX, {"head": _blog_head()}),
] + [
    (p["path"], p["page_title"], p["description"], p["body"],
     {"og_type": "article", "lastmod": p["date"], "head": _post_head(p)})
    for p in POSTS
]
