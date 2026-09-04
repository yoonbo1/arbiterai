"""Score clinical_facts against the synthetic manifest's gold_facts.

Run after the corpus has been ingested with the annotate node enabled:
  set -a; . ./.env.dev-tenant; set +a
  .venv/bin/python eval/run_extraction_eval.py --manifest data/synthetic/manifest.json [--limit 20]

DATABASE_URL must be the app_rw role (RLS-bound); TENANT_ID selects the tenant. Reports, per
fact kind, precision / recall / F1 with the rules that matter clinically:
  * a problem counts only if its assertion matches (present vs absent vs family);
  * a medication counts on name, and separately on name+dose+frequency;
  * a lab counts on test+value; a vital on test+value; an allergy on substance.
Text is de-identified in the table, which is fine: none of the gold facts are identifiers."""
import argparse, json, os, re
from collections import defaultdict

import psycopg

LAB_ALIASES = {"hba1c": {"hba1c", "a1c", "hemoglobin a1c", "glycated hemoglobin", "hgba1c"},
               "ldl": {"ldl", "ldl cholesterol", "ldl-c", "low density lipoprotein"}}
VITAL_ALIASES = {"bp": {"bp", "blood pressure", "systolic/diastolic"}}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def canon_test(name, table):
    n = norm(name)
    for k, aliases in table.items():
        if n == k or n in aliases:
            return k
    return n


def num(v):
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group()) if m else None


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def score_set(gold: set, pred: set):
    return len(gold & pred), len(pred - gold), len(gold - pred)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True); ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--min-confidence", type=float, default=0.0)
    a = ap.parse_args()
    recs = json.load(open(a.manifest))[: a.limit]
    gold_by_pid = {r["patient_external_id"]: r["gold_facts"] for r in recs if "gold_facts" in r}
    if not gold_by_pid:
        raise SystemExit("manifest has no gold_facts; regenerate with scripts/make_synthetic_docs.py")

    with psycopg.connect(os.environ["DATABASE_URL"]) as con:
        if con.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
            raise SystemExit("DATABASE_URL must use the RLS-bound app role (app_rw)")
        con.execute("SELECT set_config('app.tenant_id', %s, false)", (os.environ["TENANT_ID"],))
        rows = con.execute(
            """SELECT p.external_id, f.kind, f.normalized, f.attributes, f.assertion, f.confidence, f.extractor
                 FROM clinical_facts f JOIN patients p ON p.id = f.patient_id
                WHERE p.external_id = ANY(%s) AND f.confidence >= %s""",
            (list(gold_by_pid), a.min_confidence)).fetchall()

    pred = defaultdict(lambda: defaultdict(set))
    extractors = defaultdict(int)
    for pid, kind, normalized, attrs, assertion, conf, extractor in rows:
        attrs = attrs or {}
        extractors[extractor] += 1
        if kind == "problem":
            pred[pid]["problem"].add((norm(normalized), assertion))
        elif kind == "medication":
            pred[pid]["med_name"].add(norm(normalized))
            pred[pid]["med_full"].add((norm(normalized), norm(attrs.get("dose")), norm(attrs.get("frequency"))))
        elif kind == "lab":
            pred[pid]["lab"].add((canon_test(normalized, LAB_ALIASES), num(attrs.get("value"))))
        elif kind == "vital":
            pred[pid]["vital"].add((canon_test(normalized, VITAL_ALIASES), norm(attrs.get("value"))))
        elif kind == "allergy":
            pred[pid]["allergy"].add(norm(normalized))

    totals = defaultdict(lambda: [0, 0, 0])
    missed_examples = defaultdict(list)
    for pid, g in gold_by_pid.items():
        gold = {
            "problem": ({(norm(x), "present") for x in g["problems_present"]}
                        | {(norm(x), "absent") for x in g["problems_absent"]}
                        | {(norm(x), "family") for x in g["problems_family"]}),
            "med_name": {norm(m["name"]) for m in g["medications"]},
            "med_full": {(norm(m["name"]), norm(m["dose"]), norm(m["frequency"])) for m in g["medications"]},
            "lab": {(canon_test(l["test"], LAB_ALIASES), float(l["value"])) for l in g["labs"]},
            "vital": {(canon_test(v["test"], VITAL_ALIASES), norm(v["value"])) for v in g["vitals"]},
            "allergy": {norm(al["substance"]) for al in g["allergies"]},
        }
        for kind, gset in gold.items():
            tp, fp, fn = score_set(gset, pred[pid][kind])
            t = totals[kind]; t[0] += tp; t[1] += fp; t[2] += fn
            if fn and len(missed_examples[kind]) < 3:
                missed_examples[kind].append({"patient": pid, "missed": sorted(map(str, gset - pred[pid][kind]))[:3]})
            if fp and len(missed_examples[kind + "_spurious"]) < 3:
                missed_examples[kind + "_spurious"].append({"patient": pid, "extra": sorted(map(str, pred[pid][kind] - gset))[:3]})

    # The safety-relevant number: negated or family-history conditions wrongly stored as present.
    wrongly_present = 0
    for pid, g in gold_by_pid.items():
        bad = {norm(x) for x in g["problems_absent"]} | {norm(x) for x in g["problems_family"]}
        wrongly_present += sum(1 for (n, asrt) in pred[pid]["problem"] if n in bad and asrt == "present")

    report = {"docs": len(gold_by_pid), "facts_scored": len(rows), "by_extractor": dict(extractors),
              "metrics": {k: dict(zip(("precision", "recall", "f1"), prf(*v))) for k, v in totals.items()},
              "negated_or_family_stored_as_present": wrongly_present,
              "examples": dict(missed_examples)}
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
