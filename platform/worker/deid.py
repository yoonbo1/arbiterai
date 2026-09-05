"""De-identification with Microsoft Presidio. Covers the 18 HIPAA Safe Harbor identifiers
plus custom recognizers for MRNs, NANP phone numbers, title-anchored clinician/patient names,
and US street addresses / ZIP codes (none of which Presidio's defaults catch reliably). Each
custom recognizer and result filter lives in its own module under worker/recognizers/, with
presidio-analyzer as its only dependency. Returns reversible tokens so the final answer can be
re-identified for the authorized caller.

The spaCy model is configurable (SPACY_MODEL, default en_core_web_lg = Presidio's default);
tests can run with en_core_web_sm. The analyzer is built lazily on first use."""
import os, re, threading

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

from .recognizers import custom_recognizers
from .recognizers.address import address_recognizer
from .recognizers.date_filter import is_identifying_date as _is_identifying_date
from .recognizers.person_trim import trim_person as _trim_person

SPACY_MODEL = os.environ.get("SPACY_MODEL") or "en_core_web_lg"

ENTITIES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "LOCATION", "DATE_TIME",
            "MEDICAL_LICENSE", "URL", "IP_ADDRESS", "US_DRIVER_LICENSE", "CREDIT_CARD", "MRN"]
_TOKEN = re.compile(r"<([A-Z_]+)_(\d+)>")
_CITATION = re.compile(r"\[\d+\]")          # excerpt citations like [1234]; not identifiers

_analyzer: AnalyzerEngine | None = None
_lock = threading.Lock()


def analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        with _lock:
            if _analyzer is None:
                provider = NlpEngineProvider(nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": SPACY_MODEL}]})
                eng = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
                for recognizer in custom_recognizers():      # MRN, phone, clinician name, address
                    eng.registry.add_recognizer(recognizer)
                _analyzer = eng
    return _analyzer


def _select(results: list[RecognizerResult]) -> list[RecognizerResult]:
    """Presidio may return overlapping spans (an MRN-shaped digit run inside a phone number, a
    city NER hit inside a 'City, ST 12345' line). Overlapping candidates are merged into their
    union, so no fragment of any candidate above threshold ever survives; the merged span takes
    the entity type of its highest-scoring (then longest) member. Empty spans are dropped.
    Returned in reverse text order so in-place replacement never shifts a later span."""
    groups: list[dict] = []
    for r in sorted((r for r in results if r.end > r.start), key=lambda r: (r.start, -(r.end - r.start))):
        if groups and r.start < groups[-1]["end"]:
            g = groups[-1]
            g["end"] = max(g["end"], r.end)
            b = g["best"]
            if (r.score, r.end - r.start) > (b.score, b.end - b.start):
                g["best"] = r
        else:
            groups.append({"start": r.start, "end": r.end, "best": r})
    merged = [RecognizerResult(entity_type=g["best"].entity_type, start=g["start"], end=g["end"],
                               score=g["best"].score) for g in groups]
    return sorted(merged, key=lambda r: r.start, reverse=True)


class Scrubber:
    """Replaces PHI spans with reversible tokens. One instance per document so the same value
    maps to the same token on every page (coherence for the model and the phi_map)."""

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold
        self.phi_map: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        self._seen: dict[str, str] = {}

    def __call__(self, text: str) -> str:
        if not text or not text.strip():
            return text
        results = analyzer().analyze(text=text, entities=ENTITIES, language="en",
                                     score_threshold=self.threshold)
        # Safe Harbor dates are dates tied to a person; 'daily', 'in 2 weeks' are dosing content.
        results = [r for r in results
                   if r.entity_type != "DATE_TIME" or _is_identifying_date(text[r.start:r.end])]
        for r in results:                       # regex spans can start/end on whitespace
            while r.start < r.end and text[r.start].isspace():
                r.start += 1
            while r.end > r.start and text[r.end - 1].isspace():
                r.end -= 1
        kept = []
        for r in results:
            if r.entity_type == "PERSON":       # titles and field labels are not names
                trimmed = _trim_person(text, r.start, r.end)
                if trimmed is None:
                    continue
                r.start, r.end = trimmed
            kept.append(r)
        results = kept
        for r in _select(results):
            value = text[r.start:r.end]
            token = self._seen.get(value)
            if token is None:
                self._counters[r.entity_type] = self._counters.get(r.entity_type, 0) + 1
                token = f"<{r.entity_type}_{self._counters[r.entity_type]}>"
                self._seen[value] = token
                self.phi_map[token] = value
            text = text[:r.start] + token + text[r.end:]
        return text


def scrub(text: str, threshold: float = 0.5) -> tuple[str, dict[str, str]]:
    s = Scrubber(threshold)
    return s(text), s.phi_map


def scrub_pages(texts: list[str], threshold: float = 0.5) -> tuple[list[str], dict[str, str]]:
    """Scrub page texts one by one with shared token state. Output length always equals input
    length: no join/split on a separator that page text could itself contain."""
    s = Scrubber(threshold)
    out = [s(t) for t in texts]
    assert len(out) == len(texts), "page count changed during de-identification"
    return out, s.phi_map


def restore(text: str, phi_map: dict[str, str]) -> str:
    return _TOKEN.sub(lambda m: phi_map.get(m.group(0), m.group(0)), text)


_address_check = address_recognizer()       # pattern-only; needs no NLP artifacts


def _is_leak(hit: RecognizerResult, text: str) -> bool:
    """The scrub's own criteria: a DATE_TIME hit is an identifier only if calendar-like; a
    LOCATION hit only if the address recognizer produced it (spaCy's bare 'Texas' is not); a
    PERSON hit only if something is left after the title/label trim (the title-anchored name
    recognizer matches the bare 'Dr' in 'Attending: Dr. <PERSON_2>', which is not a name)."""
    if hit.entity_type == "DATE_TIME":
        return _is_identifying_date(text[hit.start:hit.end])
    if hit.entity_type == "LOCATION":
        return (hit.recognition_metadata or {}).get(RecognizerResult.RECOGNIZER_NAME_KEY) == _address_check.name
    if hit.entity_type == "PERSON":
        return _trim_person(text, hit.start, hit.end) is not None
    return True


def contains_phi(text: str, threshold: float = 0.5) -> bool:
    """Leak check on model output. Tokens like <PERSON_1> and citations like [12] are fine;
    raw identifiers are not. Validation runs before re-identification, so the answer still
    holds placeholders and a raw calendar date or street address / ZIP / 'City, ST' in it can
    only have come from a chunk the de-identifier missed. Dosing frequencies and durations
    ('daily', 'for 2 weeks') and bare state or country names ('Texas') are clinical content and
    pass, exactly as they survive the scrub (docs/HIPAA_CONTROLS.md, "Output leak check")."""
    stripped = _CITATION.sub("", _TOKEN.sub("", text))
    hits = analyzer().analyze(text=stripped, entities=ENTITIES, language="en", score_threshold=threshold)
    if any(_is_leak(h, stripped) for h in hits):
        return True
    # Presidio drops a pattern hit that lies inside a same-typed, higher-scoring NER hit, so an
    # address spaCy also tagged as LOCATION can be missing from `hits`; ask the patterns directly.
    return any(h.score >= threshold for h in _address_check.analyze(stripped, ["LOCATION"]))
