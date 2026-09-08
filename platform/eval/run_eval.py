"""100-request test harness. Ingests the synthetic corpus, asks gold questions, and reports:
de-id recall on injected PHI (whole-string and strict per-component), cross-patient leak
count, answer accuracy (strict and lenient), validation failures, escalations, p50/p95
latency, tokens and cost per query.
Usage (from platform/, gateway on localhost:8080, postgres published on 127.0.0.1:${PG_HOST_PORT}):
  API_KEY=hipaa_live_... TENANT_ID=<uuid> \
  DATABASE_URL=postgresql://app_rw:<PG_APP_PASSWORD>@127.0.0.1:${PG_HOST_PORT:-5432}/hipaa \
  python eval/run_eval.py --manifest data/synthetic/manifest.json [--limit N]
DATABASE_URL must be the app_rw role: the de-id/leak check reads chunks under RLS with
app.tenant_id set, which only means something for a role that RLS applies to."""
import argparse, collections, json, math, os, statistics, time
from pathlib import Path

import httpx
import psycopg

GW = os.environ.get("GATEWAY", "http://localhost:8080")
H = {"Authorization": f"Bearer {os.environ['API_KEY']}"}


def wait(job_id, timeout=900):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = httpx.get(f"{GW}/v1/jobs/{job_id}", headers=H, timeout=30)
        r.raise_for_status()
        j = r.json()
        if j["status"] in ("done", "failed"):
            return j, time.time() - t0
        time.sleep(1)
    return {"status": "timeout"}, timeout


def p95(xs):
    if not xs:
        return None
    return sorted(xs)[max(0, math.ceil(0.95 * len(xs)) - 1)]



# ---- grading by question kind ------------------------------------------------------------
# `extract` is the original substring check. The other three kinds cannot be graded that way:
# for a denial the gold string is the condition itself, so a substring match scores "the patient
# has pneumonia" as correct. Grading them wrong would inflate accuracy, which is the failure the
# de-id recall metric already made once.
NEG_CUES = ("no evidence", "no known", "denies", "denied", "ruled out", "negative for",
            "does not have", "did not have", "absence of", "not present", "no ")
FAM_CUES = ("family history", "family member", "relative", "mother", "father", "parent", "sibling")
ABS_CUES = ("not documented", "not mentioned", "no information", "not available", "not provided",
            "not stated", "no mention", "not in the record", "does not contain", "cannot determine",
            "unable to", "not specified", "no data")


def _has(text, cues):
    return any(c in text for c in cues)


def grade(kind, gold, ans, declined):
    """Returns (correct, lenient). `declined` is True when validation returned no answer."""
    a = ans.lower()
    if kind == "absent":
        # The note never contains this. Refusing is right; so is saying it is undocumented.
        # Producing a value is a fabrication, however well formed.
        ok = declined or _has(a, ABS_CUES)
        return ok, ok
    if declined:
        return False, False
    if kind == "deny":
        # Must say the finding is absent, and must not assert it as a present problem.
        ok = _has(a, NEG_CUES) and not any(
            p in a for p in (f"has {gold}", f"with {gold}", f"diagnosed with {gold}", f"treated for {gold}"))
        return ok, ok
    if kind == "family":
        # Documented in the family, not the patient. Attributing it to the patient is the error.
        ok = _has(a, FAM_CUES) and not any(
            p in a for p in (f"patient has {gold}", f"diagnosed with {gold}", f"history of {gold} in the patient"))
        return ok, ok
    items = [g.strip() for g in gold.split(";")]
    return (items[0].lower() in a,
            all(" ".join(g.split()[:2]).lower() in a for g in items))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--manifest", required=True); ap.add_argument("--limit", type=int, default=100)
    a = ap.parse_args(); recs = json.load(open(a.manifest))[: a.limit]
    root = Path(a.manifest).parent
    # 1) ingest
    for r in recs:
        path = root / ("scan" if (root / "scan" / f"{r['patient_external_id']}.pdf").exists() else "clean") / f"{r['patient_external_id']}.pdf"
        r["job"] = httpx.post(f"{GW}/v1/documents", headers=H, json={"patient_external_id": r["patient_external_id"],
                              "doc_type": "discharge_summary", "storage_uri": f"/data/synthetic/{path.parent.name}/{path.name}"}).json()["job_id"]
    for r in recs:
        wait(r["job"])
    # 2) de-id recall: does any injected PHI string survive in stored chunks?
    with psycopg.connect(os.environ["DATABASE_URL"]) as con:
        if con.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
            raise SystemExit("DATABASE_URL must use the RLS-bound app role (app_rw), not the owner/superuser")
        con.execute("SELECT set_config('app.tenant_id', %s, false)", (os.environ["TENANT_ID"],))
        text = " ".join(t for (t,) in con.execute("SELECT text FROM chunks").fetchall())
    phi = [p for r in recs for p in r["injected_phi"]]
    leaked = [p for p in phi if p in text]
    # Strict variant: a multi-part identifier (an address is "street, city, state zip") counts
    # as leaked if ANY part survives. The whole-string check above passes when only the city was
    # tokenized, which hides street lines and ZIP codes left in the index.
    parts = [(p, part.strip()) for p in phi for part in p.split(",") if len(part.strip()) >= 4]
    leaked_parts = sorted({part for _, part in parts if part in text})
    # 3) gold questions
    lat, correct, lenient, leaks, failed, esc = [], 0, 0, 0, 0, 0
    by_kind = collections.defaultdict(lambda: [0, 0])       # kind -> [correct, asked]
    query_jobs = []
    for r in recs:
        for qa in r["gold_qa"]:
            jid = httpx.post(f"{GW}/v1/queries", headers=H, json={"patient_external_id": r["patient_external_id"], "question": qa["q"]}, timeout=30).json()["job_id"]
            query_jobs.append(jid)
            res, dt = wait(jid); lat.append(dt)
            ans = (res.get("result") or {}).get("answer") or ""
            declined = res.get("status") != "done"          # validation returned no answer
            # A refusal is the correct outcome for an `absent` question, so it is not a failure.
            failed += declined and qa.get("kind") != "absent"
            # jobs.result_enc is ciphertext in the database; the gateway decrypts it for the owning
            # key, so escalations are counted from the API response, not from the table.
            esc += int(((res.get("result") or {}).get("validation") or {}).get("attempts") or 0) > 1
            c, l = grade(qa.get("kind", "extract"), qa["a"], ans, declined)
            correct += c; lenient += l
            by_kind[qa.get("kind", "extract")][0] += c
            by_kind[qa.get("kind", "extract")][1] += 1
            leaks += any(p in ans for o in recs if o is not r for p in o["injected_phi"])  # cross-patient leak
    n = sum(len(r["gold_qa"]) for r in recs)
    # 4) per-job accounting for this run (jobs is under RLS; app.tenant_id is still set). Only the
    #    plaintext accounting columns are read; request_enc / result_enc stay sealed.
    with psycopg.connect(os.environ["DATABASE_URL"]) as con:
        con.execute("SELECT set_config('app.tenant_id', %s, false)", (os.environ["TENANT_ID"],))
        ts, tl, cents = con.execute(
            """SELECT coalesce(sum(tokens_small),0), coalesce(sum(tokens_large),0), coalesce(sum(cost_cents),0)
                 FROM jobs WHERE id = ANY(%s::uuid[])""", (query_jobs,)).fetchone()
    print(json.dumps({
        "docs": len(recs), "queries": n,
        "deid_recall": 1 - len(leaked) / max(1, len(phi)), "phi_survivors": leaked[:5],
        "deid_recall_strict": 1 - len(leaked_parts) / max(1, len({part for _, part in parts})),
        "phi_component_survivors": leaked_parts[:8],
        "answer_accuracy": correct / n, "answer_accuracy_lenient": lenient / n,
        "accuracy_by_kind": {k: round(c / a, 3) for k, (c, a) in sorted(by_kind.items())},
        "questions_by_kind": {k: a for k, (c, a) in sorted(by_kind.items())},
        "queries_failed_validation": failed, "queries_escalated": esc,
        "cross_patient_leaks": leaks,
        "p50_s": statistics.median(lat) if lat else None, "p95_s": p95(lat),
        "tokens_small": int(ts), "tokens_large": int(tl), "cost_cents": float(cents),
        "cost_cents_per_query": float(cents) / max(1, n),
    }, indent=1))


if __name__ == "__main__":
    main()
