"""Page loading and text extraction with cost-aware routing: native text (free) ->
OCR (cheap) -> VLM (expensive). All runs on local hardware.

Pages carry PNG bytes, not PIL images, so graph state stays serializable; the PIL image
is built on demand."""
import base64, io, os
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import httpx
import pytesseract
from PIL import Image

from .llm import total_tokens

VLM_URL = os.environ.get("VLM_URL", "").strip().rstrip("/")     # empty => no VLM available
VLM_MODEL = os.environ.get("VLM_MODEL") or "Qwen/Qwen2.5-VL-7B-Instruct"
DATA_ROOT = Path(os.environ.get("DATA_ROOT", "/data"))
LLM_TIMEOUT_S = float(os.environ.get("LLM_TIMEOUT_S", "300"))


def vlm_available() -> bool:
    return bool(VLM_URL)


@dataclass
class Page:
    number: int
    native_text: str
    png: bytes                    # rendered page image (PNG); serializable, unlike a PIL Image
    route: str = "text"           # text | ocr | vlm  (what actually ran)
    ocr_conf: float = 0.0
    vlm_wanted: bool = False      # router chose VLM but none is configured -> OCR fallback

    def image(self) -> Image.Image:
        return Image.open(io.BytesIO(self.png))


def resolve_storage_uri(uri: str) -> Path:
    """storage_uri is client-supplied. Only files under DATA_ROOT may be opened; symlinks are
    resolved before the check so they cannot escape either. Messages never echo the URI."""
    root = DATA_ROOT.resolve()
    raw = Path(str(uri))
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise PermissionError(f"storage_uri must be a path under DATA_ROOT ({DATA_ROOT})")
    if not resolved.is_file():
        raise FileNotFoundError(f"storage_uri does not exist under DATA_ROOT ({DATA_ROOT})")
    return resolved


def load_pages(uri: str, dpi: int = 200) -> list[Page]:
    path = resolve_storage_uri(uri)
    doc = fitz.open(str(path))
    try:
        pages = []
        for i, p in enumerate(doc):
            pix = p.get_pixmap(dpi=dpi)
            pages.append(Page(i + 1, p.get_text("text").strip(), pix.tobytes("png")))
    finally:
        doc.close()
    return pages


def _conf(c) -> float | None:
    try:
        v = float(c)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None      # tesseract uses -1 for non-word boxes


def choose_route(p: Page) -> str:
    if len(p.native_text) > 200:
        return "text"
    data = pytesseract.image_to_data(p.image(), output_type=pytesseract.Output.DICT)
    confs = [v for v in (_conf(c) for c in data["conf"]) if v is not None]
    p.ocr_conf = sum(confs) / len(confs) if confs else 0.0
    words = sum(1 for w in data["text"] if str(w).strip())
    # Low confidence, very few words (likely a form/table/image), or dense layout -> VLM
    if p.ocr_conf < 75 or words < 40:
        if vlm_available():
            return "vlm"
        p.vlm_wanted = True       # keep usage stats honest: VLM was wanted, OCR ran instead
    return "ocr"


def ocr(p: Page) -> str:
    return pytesseract.image_to_string(p.image())


def vlm(p: Page) -> tuple[str, int]:
    if not vlm_available():
        raise RuntimeError("VLM_URL is not configured; route_pages should have chosen 'ocr'")
    b64 = base64.b64encode(p.png).decode()
    prompt = ("Transcribe this medical document page faithfully. Preserve headings, tables "
              "(as markdown), checkbox states, and handwritten values. Do not summarize or infer.")
    r = httpx.post(f"{VLM_URL}/chat/completions", timeout=LLM_TIMEOUT_S, json={
        "model": VLM_MODEL, "max_tokens": 2048, "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}]})
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"] or "", total_tokens(j)
