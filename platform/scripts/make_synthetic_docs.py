"""Generate synthetic clinical PDFs with KNOWN fake PHI for testing de-id recall.
Produces clean PDFs, 'scanned' PDFs (rasterized + noise), and a manifest of injected PHI.
No real patient data is involved. Usage: python scripts/make_synthetic_docs.py --n 100

For richer records, run Synthea (https://github.com/synthetichealth/synthea) and point
--synthea_csv at its patients.csv; this script will use those names/DOBs instead of Faker."""
import argparse, csv, io, json, random
from pathlib import Path

from faker import Faker
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import fitz

fake = Faker(); Faker.seed(7); random.seed(7)
DX = ["type 2 diabetes mellitus", "hypertension", "COPD", "atrial fibrillation", "CKD stage 3",
      "community-acquired pneumonia", "major depressive disorder", "osteoarthritis"]
MEDS = ["metformin 500 mg BID", "lisinopril 10 mg daily", "atorvastatin 40 mg nightly",
        "apixaban 5 mg BID", "albuterol PRN", "sertraline 50 mg daily"]
# Structured views of MEDS for extraction gold: name, dose, frequency.
MED_PARTS = {"metformin 500 mg BID": ("metformin", "500 mg", "BID"),
             "lisinopril 10 mg daily": ("lisinopril", "10 mg", "daily"),
             "atorvastatin 40 mg nightly": ("atorvastatin", "40 mg", "nightly"),
             "apixaban 5 mg BID": ("apixaban", "5 mg", "BID"),
             "albuterol PRN": ("albuterol", None, "PRN"),
             "sertraline 50 mg daily": ("sertraline", "50 mg", "daily")}
# Negated findings, family history, allergies: the extraction eval must NOT turn these into
# present problems (assertion status is the whole point of clinical NLP).
NEGATED = ["pneumonia", "chest pain", "shortness of breath", "fever", "syncope"]
FAMILY = ["coronary artery disease", "breast cancer", "stroke", "type 2 diabetes mellitus"]
ALLERGIES = [("penicillin", "rash"), ("sulfa", "hives"), ("NKDA", None), ("codeine", "nausea")]


def record(i, synth=None):
    name = synth["name"] if synth else fake.name()
    dob = synth["dob"] if synth else fake.date_of_birth(minimum_age=20, maximum_age=90).isoformat()
    return {
        "patient_external_id": f"P{i:05d}", "name": name, "dob": dob,
        "mrn": f"{random.randint(1000000, 9999999)}", "phone": fake.phone_number(),
        "address": fake.address().replace("\n", ", "), "physician": f"Dr. {fake.last_name()}",
        "visit_date": fake.date_this_year().isoformat(),
        "dx": random.sample(DX, 2), "meds": random.sample(MEDS, 3),
        "a1c": round(random.uniform(5.4, 9.8), 1), "bp": f"{random.randint(110,165)}/{random.randint(65,98)}",
        "ldl": random.randint(70, 190),
        "negated": random.sample(NEGATED, 2), "family": random.choice(FAMILY),
        "allergy": random.choice(ALLERGIES),
    }


def write_pdf(rec, path):
    c = canvas.Canvas(str(path), pagesize=letter); w, h = letter; y = h - 60
    def line(t, dy=16, bold=False):
        nonlocal y; c.setFont("Helvetica-Bold" if bold else "Helvetica", 10); c.drawString(50, y, t); y -= dy
    line("DISCHARGE SUMMARY", 22, True)
    line(f"Patient: {rec['name']}    DOB: {rec['dob']}    MRN: {rec['mrn']}")
    line(f"Phone: {rec['phone']}    Address: {rec['address']}")
    line(f"Attending: {rec['physician']}    Date of service: {rec['visit_date']}", 24)
    line("Diagnoses", 16, True); [line(f"  - {d}") for d in rec["dx"]]
    neg = rec["negated"]
    line(f"  - No evidence of {neg[0]}. Denies {neg[1]}.")
    line("Medications", 16, True); [line(f"  - {m}") for m in rec["meds"]]
    al, reaction = rec["allergy"]
    line("Allergies", 16, True); line(f"  {al}" + (f" ({reaction})" if reaction else ""))
    line("Vitals and labs", 16, True); line(f"  BP {rec['bp']}   HbA1c {rec['a1c']}%   LDL {rec['ldl']} mg/dL")
    line("Plan", 16, True)
    line(f"  Follow up with {rec['physician']} in 2 weeks. Continue current medications. Low-sodium diet.")
    line(f"  Family history of {rec['family']}.")
    c.showPage(); c.save()


def scan_it(src, dst, mode="gray"):
    """Rasterize, tilt, blur, threshold, and embed with no text layer, the way a scan or fax
    arrives. The image goes in as a compressed stream, ~45 KB per page for grayscale; inserting
    a decoded bitmap (the original code) produced ~2 MB per page.
      gray    : 150 dpi 8-bit grayscale PNG. Pixel-identical to the validated corpus. Default.
      bilevel : 300 dpi 1-bit PNG, hard threshold, no dither; fax-like, ~30 KB. Tesseract reads
                1-bit pages worse at 150 dpi, so bilevel is only offered at 300."""
    dpi = 300 if mode == "bilevel" else 150
    doc = fitz.open(src); out = fitz.open()
    for p in doc:
        pix = p.get_pixmap(dpi=dpi); img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img = img.rotate(random.uniform(-1.5, 1.5), fillcolor="white", expand=False)
        img = img.filter(ImageFilter.GaussianBlur(0.6 * dpi / 150)).convert("L").point(lambda v: 255 if v > 165 else v)
        if mode == "bilevel":
            img = img.convert("1", dither=Image.NONE)
        buf = io.BytesIO(); img.save(buf, "PNG")
        page = out.new_page(width=pix.width * 72 / dpi, height=pix.height * 72 / dpi)
        page.insert_image(page.rect, stream=buf.getvalue())
    out.save(dst, garbage=4, deflate=True); out.close()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", default="data/synthetic"); ap.add_argument("--synthea_csv")
    ap.add_argument("--scan-mode", choices=["gray", "bilevel"], default="gray")
    a = ap.parse_args(); out = Path(a.out); (out / "clean").mkdir(parents=True, exist_ok=True); (out / "scan").mkdir(exist_ok=True)
    synth = None
    if a.synthea_csv:
        with open(a.synthea_csv) as f:
            synth = [{"name": f"{r['FIRST']} {r['LAST']}", "dob": r["BIRTHDATE"]} for r in csv.DictReader(f)]
    manifest = []
    for i in range(a.n):
        rec = record(i, synth[i % len(synth)] if synth else None)
        clean = out / "clean" / f"{rec['patient_external_id']}.pdf"; write_pdf(rec, clean)
        if i % 2:  # half the corpus goes through the OCR/VLM path
            scan_it(clean, out / "scan" / clean.name, a.scan_mode)
        al, reaction = rec["allergy"]
        manifest.append({**rec, "injected_phi": [rec["name"], rec["dob"], rec["mrn"], rec["phone"], rec["address"], rec["physician"]],
                         "gold_qa": [{"q": "What is the patient's most recent HbA1c?", "a": f"{rec['a1c']}%"},
                                     {"q": "List the discharge medications.", "a": "; ".join(rec["meds"])}],
                         # Gold for the extraction eval (clinical_facts). Assertions matter: the two
                         # negated findings and the family-history condition must not appear as present.
                         "gold_facts": {
                             "problems_present": [d.lower() for d in rec["dx"]],
                             "problems_absent": [n.lower() for n in rec["negated"]],
                             "problems_family": [rec["family"].lower()],
                             "medications": [{"name": MED_PARTS[m][0], "dose": MED_PARTS[m][1], "frequency": MED_PARTS[m][2]} for m in rec["meds"]],
                             "labs": [{"test": "hba1c", "value": rec["a1c"], "unit": "%"},
                                      {"test": "ldl", "value": rec["ldl"], "unit": "mg/dL"}],
                             "vitals": [{"test": "bp", "value": rec["bp"]}],
                             "allergies": [] if al == "NKDA" else [{"substance": al.lower(), "reaction": reaction}],
                         }})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote {a.n} records to {out}")


if __name__ == "__main__":
    main()
