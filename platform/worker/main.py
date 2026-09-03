"""Worker loop: consume jobs from Redis Streams, run the right LangGraph.

Recovery model:
  * a job that raises is marked failed and acked (no automatic retry of application errors);
  * a message left pending because a worker died mid-job is reclaimed (XAUTOCLAIM) after
    WORKER_CLAIM_IDLE_MS and re-run, at most WORKER_MAX_DELIVERIES times in total;
  * SIGTERM/SIGINT finish the current job, then exit.
Logs never contain PHI: only job ids, kinds, exception class names and timings."""
import os, signal, socket, time, traceback

import redis
from psycopg.types.json import Jsonb

from . import graph, store

STREAM, GROUP = "jobs", "workers"
CONSUMER = f"{socket.gethostname()}-{os.getpid()}"
MAX_DELIVERIES = int(os.environ.get("WORKER_MAX_DELIVERIES", "3"))
CLAIM_IDLE_MS = int(os.environ.get("WORKER_CLAIM_IDLE_MS", "300000"))
DEBUG_TRACEBACKS = os.environ.get("WORKER_DEBUG_TRACEBACKS", "0") == "1"   # synthetic data only
_stop = False


class JobNotVisible(Exception):
    """The job row is not visible under the tenant in the stream message (RLS mismatch or deleted)."""


def _log(msg: str) -> None:
    print(f"[worker {CONSUMER}] {msg}", flush=True)


def _on_signal(signum, _frame):
    global _stop
    _stop = True
    _log(f"signal {signum}: finishing current job, then exiting")


def make_checkpointer(kind: str | None):
    """CHECKPOINTER=none|memory|postgres. Default none: graph state carries pre-de-identification
    text and the plaintext phi_map, so persisting it is only acceptable once it is encrypted and
    tenant-scoped. memory grows without bound in a long-running worker (tests only)."""
    kind = (kind or "none").strip().lower()
    if kind in ("", "none"):
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()
    if kind == "postgres":
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        url = os.environ.get("DATABASE_ADMIN_URL") or os.environ["DATABASE_URL"]   # needs CREATE
        conn = psycopg.connect(url, autocommit=True, prepare_threshold=0, row_factory=dict_row)
        saver = PostgresSaver(conn)
        saver.setup()
        _log("WARNING: CHECKPOINTER=postgres persists PHI-bearing graph state; synthetic data only")
        return saver
    raise ValueError(f"unknown CHECKPOINTER {kind!r} (none|memory|postgres)")


def _job(job_id: str, tenant_id: str) -> dict | None:
    with store.tenant_conn(tenant_id) as con:
        row = con.execute("SELECT api_key_id, kind, request FROM jobs WHERE id=%s", (job_id,)).fetchone()
        if row is None:
            return None
        con.execute("UPDATE jobs SET status='processing' WHERE id=%s", (job_id,))
    return {"api_key_id": str(row[0]), "kind": row[1], "request": row[2]}


def _patient(con, tenant_id: str, external_id: str) -> str:
    return str(con.execute(
        "INSERT INTO patients (tenant_id, external_id) VALUES (%s,%s) "
        "ON CONFLICT (tenant_id, external_id) DO UPDATE SET external_id=EXCLUDED.external_id RETURNING id",
        (tenant_id, external_id)).fetchone()[0])


def handle(job_id: str, tenant_id: str, ingest_app, query_app) -> str:
    j = _job(job_id, tenant_id)
    if j is None:
        raise JobNotVisible(job_id)
    req = j["request"]
    base = {"job_id": job_id, "tenant_id": tenant_id, "api_key_id": j["api_key_id"], "kind": j["kind"]}
    cfg = {"configurable": {"thread_id": job_id}}          # harmless without a checkpointer
    doc_id = None
    with store.tenant_conn(tenant_id) as con:
        pid = _patient(con, tenant_id, req["patient_external_id"])
        if j["kind"] == "ingest":
            # Same storage_uri for the same tenant = same document: reuse its id so re-ingest
            # replaces the derived rows instead of orphaning a never-inserted doc_id.
            doc_id = str(con.execute(
                "INSERT INTO documents (tenant_id, patient_id, doc_type, storage_uri, content_hash, status) "
                "VALUES (%s,%s,%s,%s,md5(%s),'processing') "
                "ON CONFLICT (tenant_id, content_hash) DO UPDATE "
                "SET status='processing', patient_id=EXCLUDED.patient_id, doc_type=EXCLUDED.doc_type "
                "RETURNING id",
                (tenant_id, pid, req.get("doc_type"), req["storage_uri"], req["storage_uri"])).fetchone()[0])
    try:
        if j["kind"] == "ingest":
            ingest_app.invoke({**base, "patient_id": pid, "storage_uri": req["storage_uri"],
                               "doc_type": req.get("doc_type"), "document_id": doc_id}, cfg)
        elif j["kind"] == "query":
            query_app.invoke({**base, "patient_id": pid, "question": req["question"],
                              "max_chunks": req.get("max_chunks", 6)}, cfg)
        else:
            raise ValueError(f"unsupported job kind {j['kind']!r}")
    except Exception:
        if doc_id:
            with store.tenant_conn(tenant_id) as con:
                con.execute("UPDATE documents SET status='failed' WHERE id=%s", (doc_id,))
        raise
    return j["kind"]


def _mark_failed(job_id: str, tenant_id: str, reason: str) -> None:
    try:
        with store.tenant_conn(tenant_id) as con:
            con.execute("UPDATE jobs SET status='failed', result=%s, finished_at=now() WHERE id=%s AND status<>'done'",
                        (Jsonb({"error": reason}), job_id))
    except Exception as e:           # DB down: log and move on, never kill the loop
        _log(f"{job_id} could not be marked failed: {type(e).__name__}")


def _safe_ack(r, msg_id: str) -> None:
    try:
        r.xack(STREAM, GROUP, msg_id)
    except Exception as e:
        _log(f"xack {msg_id} failed: {type(e).__name__}")


def _deliveries(r, msg_id: str) -> int:
    try:
        p = r.xpending_range(STREAM, GROUP, min=msg_id, max=msg_id, count=1)
        return int(p[0]["times_delivered"]) if p else 1
    except Exception:
        return 1


def _claim_stalled(r) -> list[tuple[str, dict]]:
    """Messages pending for longer than CLAIM_IDLE_MS belong to a worker that died mid-job."""
    try:
        res = r.xautoclaim(STREAM, GROUP, CONSUMER, min_idle_time=CLAIM_IDLE_MS, start_id="0-0", count=10)
    except redis.ResponseError:
        return []
    entries = res[1] if isinstance(res, (list, tuple)) and len(res) >= 2 else []
    return [(mid, data) for mid, data in entries if data]


def _process(r, msg_id: str, data: dict, ingest_app, query_app) -> None:
    job_id, tenant_id, kind = data.get("job_id"), data.get("tenant_id"), data.get("kind", "?")
    t0 = time.time()
    if not job_id or not tenant_id:
        _log(f"malformed message {msg_id}; dropping")
        _safe_ack(r, msg_id)
        return
    try:
        n = _deliveries(r, msg_id)
        if n > MAX_DELIVERIES:
            _log(f"{kind} {job_id} delivered {n} times (limit {MAX_DELIVERIES}); marking failed")
            _mark_failed(job_id, tenant_id, "max_deliveries_exceeded")
            _safe_ack(r, msg_id)
            return
        if n > 1:
            _log(f"{kind} {job_id} re-delivered (attempt {n})")
        handle(job_id, tenant_id, ingest_app, query_app)
        _safe_ack(r, msg_id)
        _log(f"{kind} {job_id} ok {time.time() - t0:.1f}s")
    except JobNotVisible:
        _log(f"{kind} {job_id} not visible for its tenant (RLS mismatch or deleted); dropping")
        _safe_ack(r, msg_id)
    except Exception as e:
        _log(f"{kind} {job_id} FAILED {type(e).__name__} after {time.time() - t0:.1f}s")
        if DEBUG_TRACEBACKS:
            traceback.print_exc()
        _mark_failed(job_id, tenant_id, type(e).__name__)
        _safe_ack(r, msg_id)


def main():
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    r = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise
    saver = make_checkpointer(os.environ.get("CHECKPOINTER"))
    ingest_app = graph.build_ingest().compile(checkpointer=saver)
    query_app = graph.build_query().compile(checkpointer=saver)
    store.get_pool().wait(timeout=60)      # fail fast if Postgres is unreachable
    _log(f"ready (checkpointer={os.environ.get('CHECKPOINTER') or 'none'}, "
         f"max_deliveries={MAX_DELIVERIES}, claim_idle_ms={CLAIM_IDLE_MS})")
    while not _stop:
        try:
            batch = _claim_stalled(r)
            if not batch:
                msgs = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=1, block=5000)
                batch = [(mid, data) for _, entries in (msgs or []) for mid, data in entries]
        except redis.ConnectionError as e:
            _log(f"redis unavailable ({type(e).__name__}); retrying in 5s")
            time.sleep(5)
            continue
        for msg_id, data in batch:
            _process(r, msg_id, data, ingest_app, query_app)
            if _stop:
                break
    _log("stopped")


if __name__ == "__main__":
    main()
