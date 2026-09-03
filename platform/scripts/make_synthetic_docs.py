"""Generate synthetic clinical PDFs with KNOWN fake PHI for testing de-id recall.
Produces clean PDFs, 'scanned' PDFs (rasterized + noise), and a manifest of injected PHI.
No real patient data is involved. Usage: python scripts/make_synthetic_docs.py --n 100

For richer records, run Synthea (https://github.com/synthetichealth/synthea) and point
--synthea_csv at its patients.csv; this script will use those names/DOBs instead of Faker."""
import argparse, csv, json, random
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
    line("Medications", 16, True); [line(f"  - {m}") for m in rec["meds"]]
    line("Vitals and labs", 16, True); line(f"  BP {rec['bp']}   HbA1c {rec['a1c']}%")
    line("Plan", 16, True)
    line(f"  Follow up with {rec['physician']} in 2 weeks. Continue current medications. Low-sodium diet.")
    c.showPage(); c.save()


def scan_it(src, dst):
    doc = fitz.open(src); out = fitz.open()
    for p in doc:
        pix = p.get_pixmap(dpi=150); img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img = img.rotate(random.uniform(-1.5, 1.5), fillcolor="white", expand=False)
        img = img.filter(ImageFilter.GaussianBlur(0.6)).convert("L").point(lambda v: 255 if v > 165 else v)
        tmp = dst.with_suffix(".png"); img.save(tmp)
        page = out.new_page(width=pix.width, height=pix.height); page.insert_image(page.rect, filename=str(tmp)); tmp.unlink()
    out.save(dst)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", default="data/synthetic"); ap.add_argument("--synthea_csv")
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
            scan_it(clean, out / "scan" / clean.name)
        manifest.append({**rec, "injected_phi": [rec["name"], rec["dob"], rec["mrn"], rec["phone"], rec["address"], rec["physician"]],
                         "gold_qa": [{"q": "What is the patient's most recent HbA1c?", "a": f"{rec['a1c']}%"},
                                     {"q": "List the discharge medications.", "a": "; ".join(rec["meds"])}]})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote {a.n} records to {out}")


if __name__ == "__main__":
    main()
