"""Minimal local embeddings service, API-compatible with the subset of HuggingFace
text-embeddings-inference (TEI) that worker.store.embed() uses:

  POST /embed   {"inputs": ["...", ...], "truncate": true}  ->  [[384 floats], ...]
  GET  /health  -> 200 {"ok": true} once the model is loaded

Exists because the TEI cpu-* images are linux/amd64 only and do not run on Apple Silicon
under Rosetta. Uses fastembed (ONNX Runtime, native arm64) with BAAI/bge-small-en-v1.5
(384 dims, normalized). The model is downloaded from the HF hub on first start into
FASTEMBED_CACHE_PATH; mount a volume there so restarts are offline."""
import os, threading
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
MAX_BATCH = int(os.environ.get("EMBED_MAX_BATCH", "64"))
MAX_CHARS = int(os.environ.get("EMBED_MAX_CHARS", "8000"))   # truncate=true caps input length

app = FastAPI(title="local embeddings")
_model: Any = None
_error: str | None = None
_lock = threading.Lock()


def _load() -> None:
    global _model, _error
    try:
        from fastembed import TextEmbedding
        m = TextEmbedding(model_name=MODEL, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))
        list(m.embed(["warmup"]))
        with _lock:
            _model = m
    except Exception as e:      # surface in /health instead of dying silently
        _error = f"{type(e).__name__}: {e}"


@app.on_event("startup")
def startup() -> None:
    threading.Thread(target=_load, daemon=True).start()


class EmbedRequest(BaseModel):
    inputs: list[str] | str = Field(description="one string or a batch")
    truncate: bool = True
    normalize: bool = True


@app.get("/health")
def health():
    if _model is not None:
        return {"ok": True, "model": MODEL}
    return JSONResponse({"ok": False, "model": MODEL, "error": _error or "loading"}, status_code=503)


@app.post("/embed")
def embed(req: EmbedRequest):
    if _model is None:
        raise HTTPException(503, _error or "model loading")
    texts = [req.inputs] if isinstance(req.inputs, str) else req.inputs
    if not texts:
        return []
    if len(texts) > MAX_BATCH:
        raise HTTPException(413, f"batch size {len(texts)} > {MAX_BATCH}")
    if req.truncate:
        texts = [t[:MAX_CHARS] for t in texts]
    elif any(len(t) > MAX_CHARS for t in texts):
        raise HTTPException(413, "input too long; set truncate=true")
    return [[float(x) for x in vec] for vec in _model.embed(texts, batch_size=len(texts))]
