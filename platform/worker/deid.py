"""De-identification with Microsoft Presidio. Covers the 18 HIPAA Safe Harbor identifiers
plus custom recognizers for MRNs, NANP phone numbers, title-anchored clinician/patient names,
and US street addresses / ZIP codes (none of which Presidio's defaults catch reliably). Returns reversible tokens so the final answer can be
re-identified for the authorized caller.

The spaCy model is configurable (SPACY_MODEL, default en_core_web_lg = Presidio's default);
tests can run with en_core_web_sm. The analyzer is built lazily on first use."""
import os, re, threading

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider

SPACY_MODEL = os.environ.get("SPACY_MODEL") or "en_core_web_lg"

ENTITIES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN", "LOCATION", "DATE_TIME",
            "MEDICAL_LICENSE", "URL", "IP_ADDRESS", "US_DRIVER_LICENSE", "CREDIT_CARD", "MRN"]
_TOKEN = re.compile(r"<([A-Z_]+)_(\d+)>")
_CITATION = re.compile(r"\[\d+\]")          # excerpt citations like [1234]; not identifiers

_analyzer: AnalyzerEngine | None = None
_lock = threading.Lock()


def _mrn_recognizer() -> PatternRecognizer:
    # Labeled form: only the digits are replaced, so "MRN: <MRN_1>" keeps its label.
    # Python lookbehinds must be fixed-width, hence one alternative per label spelling.
    labeled = r"(?<=\bMRN: )\d{6,10}\b|(?<=\bMRN:)\d{6,10}\b|(?<=\bMRN )\d{6,10}\b|(?<=\bMRN# )\d{6,10}\b|(?<=\bMRN#)\d{6,10}\b"
    return PatternRecognizer(
        supported_entity="MRN",
        patterns=[Pattern("mrn_labeled", labeled, 0.85),
                  # bare 6-10 digit run: weak alone; Presidio's context enhancer lifts it when
                  # 'mrn' / 'medical record' appears nearby.
                  Pattern("mrn_bare", r"\b\d{6,10}\b", 0.3)],
        context=["mrn", "medical record", "record number", "chart number"])


def _phone_recognizer() -> PatternRecognizer:
    """Presidio's phonenumbers-based recognizer misses common chart formats such as
    '+1-921-899-3518x19093' or '(555) 201-8842 ext. 12'. Regex backstop for NANP numbers with
    optional country code and extension; overlapping hits are resolved by _select()."""
    nanp = r"(?:\+?1[-. ])?(?:\(\d{3}\)\s?|\d{3}[-. ])\d{3}[-. ]\d{4}(?:\s*(?:x|ext\.?|extension)\s*\d{1,6})?"
    # A bare 10-digit run (Tel: 9218993518) is only a phone number when a phone-ish word is
    # nearby: 0.35 alone (below the 0.5 threshold), lifted by the context enhancer when
    # 'tel'/'phone'/'fax'... appears in the surrounding words.
    bare = r"\b(?:1[-. ]?)?[2-9]\d{2}[2-9]\d{6}\b"
    return PatternRecognizer(supported_entity="PHONE_NUMBER", name="phone_regex",
                             patterns=[Pattern("nanp_with_ext", nanp, 0.6), Pattern("nanp_bare", bare, 0.35)],
                             context=["phone", "tel", "telephone", "cell", "mobile", "fax", "call"])


_USPS_SUFFIX = (
    "Alley|Anex|Arcade|Avenue|Ave|Bayou|Beach|Bend|Bluff|Bluffs|Bottom|Boulevard|Blvd|Branch|Bridge|Brook|"
    "Brooks|Burg|Burgs|Bypass|Camp|Canyon|Cape|Causeway|Center|Centers|Circle|Circles|Cliff|Cliffs|Club|"
    "Common|Commons|Corner|Corners|Course|Court|Courts|Ct|Cove|Coves|Creek|Crescent|Crest|Crossing|Crossroad|"
    "Crossroads|Curve|Dale|Dam|Divide|Drive|Drives|Dr|Estate|Estates|Expressway|Extension|Extensions|Fall|"
    "Falls|Ferry|Field|Fields|Flat|Flats|Ford|Fords|Forest|Forge|Forges|Fork|Forks|Fort|Freeway|Garden|"
    "Gardens|Gateway|Glen|Glens|Green|Greens|Grove|Groves|Harbor|Harbors|Haven|Heights|Highway|Hwy|Hill|"
    "Hills|Hollow|Inlet|Island|Islands|Isle|Junction|Junctions|Key|Keys|Knoll|Knolls|Lake|Lakes|Land|"
    "Landing|Lane|Ln|Light|Lights|Loaf|Lock|Locks|Lodge|Loop|Mall|Manor|Manors|Meadow|Meadows|Mews|Mill|"
    "Mills|Mission|Motorway|Mount|Mountain|Mountains|Neck|Orchard|Oval|Overpass|Park|Parks|Parkway|Pkwy|"
    "Parkways|Pass|Passage|Path|Pike|Pine|Pines|Place|Pl|Plain|Plains|Plaza|Point|Points|Port|Ports|"
    "Prairie|Radial|Ramp|Ranch|Rapid|Rapids|Rest|Ridge|Ridges|River|Road|Rd|Roads|Route|Row|Rue|Run|Shoal|"
    "Shoals|Shore|Shores|Skyway|Spring|Springs|Spur|Spurs|Square|Sq|Squares|Station|Stravenue|Stream|"
    "Street|St|Streets|Summit|Terrace|Throughway|Trace|Track|Trafficway|Trail|Trl|Trailer|Tunnel|Turnpike|"
    "Underpass|Union|Unions|Valley|Valleys|Viaduct|View|Views|Village|Villages|Ville|Vista|Walk|Walks|Wall|"
    "Way|Ways|Well|Wells"
)
_UNIT = r"(?:,? ?(?:Suite|Ste\.?|Apt\.?|Apartment|Unit|Bldg\.?|Floor|Fl\.?|#) ?[\w-]+)?"


def _name_recognizer() -> PatternRecognizer:
    """spaCy NER misses 'Dr. <common-word surname>' ('Dr. Young', 'Dr. Fields') often enough to
    fail the recall gate. Anchor on the title instead; only the name is replaced so the title
    survives ('Attending: Dr. <PERSON_2>'). Lookbehinds are fixed-width, one per spelling."""
    # Presidio compiles patterns with IGNORECASE; (?-i:...) makes the name part case-sensitive so
    # it stops at the first lowercase word ("Dr. Priya Raghunathan-Okafor reviewed" -> the name only).
    name = r"(?-i:[A-Z][a-zA-Z'\-]+(?: [A-Z][a-zA-Z'\-]+){0,2})"
    pats = [Pattern(f"title_{i}", rf"(?<={lb}){name}", 0.7)
            for i, lb in enumerate((r"\bDr\. ", r"\bDr ", r"\bDoctor ", r"\bMD ", r"\bAttending: ", r"\bPhysician: ",
                                    r"\bProvider: ", r"\bPatient: ", r"\bPatient Name: ", r"\bName: "))]
    return PatternRecognizer(supported_entity="PERSON", name="title_name_regex", patterns=pats)


def _address_recognizer() -> PatternRecognizer:
    """Presidio has no US street-address recognizer; spaCy tags the city at best, leaving the
    street line and ZIP in the index. Labelled 'Address:' lines are taken whole up to the first
    comma or newline; unlabelled street lines need a number, 1-4 words, and a USPS suffix."""
    # Labelled: up to "street, city, ST ZIP" (three comma segments) after "Address:", stopping at
    # a run of spaces, the next "Label:" on the same line, or end of line.
    seg = r"(?:[^\n,]{2,60}, ){0,3}[^\n,]{2,40}?(?=\s{2,}|\s+[A-Za-z ]{2,20}:|\n|$)"
    labelled = (rf"(?<=\bAddress: ){seg}|(?<=\bAddress:)(?=\S){seg}"
                rf"|(?<=\bAddr: ){seg}|(?<=\bAddr:)(?=\S){seg}")
    street = rf"\b\d{{1,6}} (?:[A-Za-z][A-Za-z'\-]+ ){{1,4}}(?:{_USPS_SUFFIX})\b\.?{_UNIT}"
    # "City, ST 12345": spaCy misses invented or rare city names, this does not need to know them.
    city_state_zip = r"\b[A-Za-z][A-Za-z.'\- ]{1,40}, [A-Za-z]{2} \d{5}(?:-\d{4})?\b"
    return PatternRecognizer(supported_entity="LOCATION", name="street_address_regex",
                             patterns=[Pattern("address_labelled", labelled, 0.85),
                                       Pattern("street_line", street, 0.6),
                                       Pattern("city_state_zip", city_state_zip, 0.6),
                                       # A bare 5-digit run is a lab value at least as often as a ZIP
                                       # (WBC 11000, a platelet count); 0.35 alone is below the 0.5 threshold
                                       # and only the address context words above lift it.
                                       Pattern("us_zip", r"\b\d{5}(?:-\d{4})?\b", 0.35)],
                             context=["address", "street", "zip", "apt", "suite", "resides", "lives at"])


# Safe Harbor removes dates tied to a person (birth, admission, discharge, death...). spaCy's
# DATE label also covers frequencies and durations ('daily', 'nightly', 'in 2 weeks', 'tonight'),
# which are clinical content, not identifiers; redacting them destroys dosing instructions.
# Keep a DATE_TIME hit only if it contains something calendar-like.
_DATE_LIKE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\b"     # month names
    r"|\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b"                                     # 3/5/2024, 03-05-24
    r"|\b\d{4}-\d{2}-\d{2}\b"                                                     # ISO
    r"|\b(?:19|20)\d{2}\b"                                                         # a year
    r"|\b\d{1,2}(?:st|nd|rd|th)\b",                                                # 5th (of March)
    re.IGNORECASE)


def _is_identifying_date(span: str) -> bool:
    return bool(_DATE_LIKE.search(span))


def analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        with _lock:
            if _analyzer is None:
                provider = NlpEngineProvider(nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [{"lang_code": "en", "model_name": SPACY_MODEL}]})
                eng = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
                eng.registry.add_recognizer(_mrn_recognizer())
                eng.registry.add_recognizer(_phone_recognizer())
                eng.registry.add_recognizer(_name_recognizer())
                eng.registry.add_recognizer(_address_recognizer())
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
        results = [r for r in results
                   if r.entity_type != "DATE_TIME" or _is_identifying_date(text[r.start:r.end])]
        for r in results:                       # regex spans can start/end on whitespace
            while r.start < r.end and text[r.start].isspace():
                r.start += 1
            while r.end > r.start and text[r.end - 1].isspace():
                r.end -= 1
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


def contains_phi(text: str, threshold: float = 0.5) -> bool:
    """Leak check on model output. Tokens like <PERSON_1> and citations like [12] are fine;
    raw identifiers are not."""
    stripped = _CITATION.sub("", _TOKEN.sub("", text))
    hits = analyzer().analyze(text=stripped, entities=ENTITIES, language="en", score_threshold=threshold)
    return any(h.entity_type not in ("DATE_TIME", "LOCATION") for h in hits)
