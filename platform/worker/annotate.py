"""Clinical annotation: DE-IDENTIFIED page text -> structured clinical facts (clinical_facts rows).

Three layers produce candidate spans, cheapest first; an earlier layer wins overlaps and later
layers only fill attributes it left empty:
  1. rules   regex over section-aware lines: labs with value/unit, vitals, allergy lines,
             medication lines (name dose route frequency), family-history phrases, follow-up
             plans.  Deterministic; confidence 0.95.
  2. ner     en_core_med7_lg (DRUG + STRENGTH/DOSAGE/FORM/ROUTE/FREQUENCY/DURATION; 0.85) and
             en_ner_bc5cdr_md (DISEASE -> problem; 0.75), run as separate pipelines on the same
             text and merged by character offsets.
  3. llm     optional (ANNOTATE_LLM=1): the small local model reads ONLY the bodies of the
             medication / allergy / diagnosis / lab / plan sections and returns a fixed JSON
             schema.  Every returned `text` must be a verbatim substring of what was sent, and
             the JSON must pass deid.contains_phi; it fills missing attributes of rule/NER facts
             and adds facts nobody else found (0.6).  It never decides assertion.

Assertion (present / absent / possible / conditional / historical / family) comes from medspaCy
ConText run over the merged entities; sections come from the medspaCy Sectionizer with the
shipped rules plus line-anchored rules for bare headers ("Diagnoses", "Meds:", "Plan").

Input is de-identified text: <PERSON_1>-style placeholders are single tokens in every tokenizer
and any span touching one is discarded, so a placeholder can never become a fact.  Nothing here
leaves the process except the optional LLM call to the local endpoint configured in llm.py.
Logs carry counts and timings only, never text.

Models are heavy (~1 GB) and are loaded lazily, once, behind a lock (see load_models); importing
this module is cheap so graph.py can be imported with ANNOTATE=0 and without medspaCy installed.
"""
from __future__ import annotations

import json, os, re, threading, time
from dataclasses import asdict, dataclass, field, replace

# PyRuSH logs every token of every document at DEBUG through loguru, which would put
# de-identified text in container logs.  Disable it at import, before PyRuSH is ever imported
# (loguru ships with medspaCy; without medspaCy there is no PyRuSH to silence).
try:
    from loguru import logger as _loguru
    _loguru.disable("PyRuSH")
except ImportError:  # pragma: no cover
    pass

from . import deid, llm

KINDS = ("problem", "medication", "lab", "vital", "allergy", "procedure", "referral", "plan", "other")
ASSERTIONS = ("present", "absent", "possible", "conditional", "historical", "family")
CONFIDENCE = {"rules": 0.95, "med7": 0.85, "bc5cdr": 0.75, "llm": 0.6}
EXTRACTOR = {"rules": "rules", "med7": "ner", "bc5cdr": "ner", "llm": "llm"}
PRIORITY = {"rules": 3, "med7": 2, "bc5cdr": 1, "llm": 0}

PLACEHOLDER = re.compile(r"<[A-Z_]+_\d+>")
DATE_TOKEN = re.compile(r"<DATE_TIME_\d+>")
_WS = re.compile(r"\s+")


@dataclass
class Fact:
    page: int                 # 1-based
    start: int                # char offsets into that page's (de-identified) text
    end: int
    kind: str                 # one of KINDS
    text: str                 # surface form, de-identified
    normalized: str           # lower-cased, whitespace-collapsed; drug name only for medications
    attributes: dict
    assertion: str            # one of ASSERTIONS
    section: str | None       # medspaCy section category
    date_token: str | None    # nearest <DATE_TIME_n> on the same page
    confidence: float
    extractor: str            # rules | ner | llm

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class _Cand:
    start: int
    end: int
    kind: str
    attributes: dict
    source: str                          # rules | med7 | bc5cdr | llm
    normalized: str | None = None        # None -> derived from the surface text
    fixed_assertion: str | None = None   # rules that know the assertion (family history)
    as_entity: bool = True               # False: long spans (plan sentences) that must not eat entities


@dataclass
class _Section:
    category: str | None
    title_start: int
    body_start: int
    body_end: int


@dataclass
class _Models:
    host: object
    med7: object
    bc5cdr: object


# ----------------------------------------------------------------------------- section rules
# Bare headers the shipped (colon-anchored) rules miss.  Matched case-insensitively at the start of
# a line, either alone on the line or followed by ':' (so "Allergies: NKDA" still works).
SECTION_HEADERS: dict[str, list[str]] = {
    "diagnoses": ["diagnoses", "diagnosis", "admission diagnoses", "discharge diagnoses", "principal diagnosis",
                  "secondary diagnoses"],
    "problem_list": ["problem list", "problems", "active problems", "active problem list"],
    "medications": ["medications", "medication", "meds", "current medications", "current meds", "home medications",
                    "home meds", "discharge medications", "discharge meds", "medication list",
                    "medications on discharge", "admission medications", "medication reconciliation"],
    "allergy": ["allergies", "allergy", "drug allergies", "allergies/adverse reactions", "allergies and intolerances"],
    "labs_and_studies": ["vitals and labs", "vitals", "vital signs", "labs", "lab results", "laboratory data",
                         "laboratory results", "laboratory", "labs and studies", "studies", "imaging", "results"],
    "observation_and_plan": ["p[il]an", "assessment and plan", "assessment/plan", "assessment & plan", "a/p", "a&p",
                             "assessment", "impression and plan", "recommendations", "disposition", "follow up",
                             "follow-up", "discharge plan", "discharge instructions"],
    "family_history": ["family history", "family hx", "fhx", "fh"],
    "past_medical_history": ["past medical history", "pmh", "pmhx", "medical history", "past surgical history",
                             "psh", "past history"],
    "social_history": ["social history", "shx", "sh"],
    "hospital_course": ["hospital course", "brief hospital course", "course"],
    "physical_exam": ["physical exam", "physical examination", "exam", "pe"],
    "history_of_present_illness": ["hpi", "history of present illness", "history of the present illness"],
    "chief_complaint": ["chief complaint", "cc", "reason for visit", "reason for admission"],
    "review_of_systems": ["review of systems", "ros"],
}
# Section attributes applied to entities.  medspaCy's default also sets is_hypothetical on the
# allergy section, which made everything after "Allergies:" conditional; that entry is dropped.
SECTION_ATTRS = {
    "family_history": {"is_family": True},
    "past_medical_history": {"is_historical": True},
    "sexual_and_social_history": {"is_historical": True},
    "patient_instructions": {"is_hypothetical": True},
    "education": {"is_hypothetical": True},
}
# Shipped rules whose literal is a bare common word: they fire mid-sentence ("denies allergies").
_DROP_DEFAULT_LITERALS = {"allergies"}
_SECTION_ALIAS = {"allergies": "allergy"}
LLM_SECTIONS = ("medications", "allergy", "diagnoses", "problem_list", "labs_and_studies", "observation_and_plan")


def _header_regex(names: list[str]) -> str:
    alts = "|".join(n if "[" in n else re.escape(n) for n in sorted(names, key=len, reverse=True))
    return rf"(?im)^[ \t]*(?:{alts})[ \t]*(?::|\r?$)"


# ----------------------------------------------------------------------------- rule patterns
_LAB_NAMES = [   # (regex, canonical normalized name)
    (r"H(?:g)?b\s?A[a-z]?[1lIi]c|A1c|Hemoglobin A1c|Glycated hemoglobin", "hba1c"),   # OCR: HbAic, HbAlc, HbAt1c
    (r"LDL(?:-C)?(?: cholesterol)?", "ldl"), (r"HDL(?:-C)?(?: cholesterol)?", "hdl"),
    (r"Total cholesterol", "total cholesterol"), (r"Triglycerides", "triglycerides"),
    (r"Na|Sodium", "sodium"), (r"K|Potassium", "potassium"), (r"Cr|Creatinine", "creatinine"),
    (r"BUN", "bun"), (r"eGFR", "egfr"), (r"Glucose", "glucose"), (r"Hgb|Hemoglobin", "hemoglobin"),
    (r"WBC", "wbc"), (r"Plt|Platelets", "platelets"), (r"TSH", "tsh"), (r"BNP", "bnp"),
]
_UNITS = r"%|mg/dL|mmol/L|g/dL|pg/mL|mEq/L|K/uL|mL/min(?:/1\.73\s?m2)?|ng/mL|IU/L|U/L|mg/L|mcg/dL"
LAB_RE = re.compile(
    r"(?<!vitamin )(?<![A-Za-z])(?P<name>" + "|".join(rx for rx, _ in _LAB_NAMES) + r")(?![A-Za-z])"
    r"\s*[:=]?\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>" + _UNITS + r")?", re.I)
_LAB_CANON = [(re.compile(rf"^(?:{rx})$", re.I), canon) for rx, canon in _LAB_NAMES]

VITAL_RES = [   # (normalized, regex, default unit)
    ("bp", re.compile(r"\b(?:BP|blood pressure)\s*[:=]?\s*(?P<value>\d{2,3}\s*/\s*\d{2,3})", re.I), "mmHg"),
    ("hr", re.compile(r"\b(?:HR|heart rate|pulse)\s*[:=]?\s*(?P<value>\d{2,3})(?![\d/])", re.I), "bpm"),
    ("rr", re.compile(r"\b(?:RR|resp(?:iratory)? rate)\s*[:=]?\s*(?P<value>\d{1,2})(?![\d/])", re.I), "/min"),
    ("spo2", re.compile(r"\b(?:SpO2|SaO2|O2 sat(?:uration)?)\s*[:=]?\s*(?P<value>\d{2,3})\s*%?", re.I), "%"),
    ("temp", re.compile(r"\b(?:Temp(?:erature)?|Tmax)\.?\s*[:=]?\s*(?P<value>\d{2,3}(?:\.\d)?)\s*(?P<unit>°\s?[FC]|[FC]\b)?", re.I), None),
    ("weight", re.compile(r"\b(?:Wt|Weight)\.?\s*[:=]?\s*(?P<value>\d{2,3}(?:\.\d+)?)\s*(?P<unit>kg|lbs?|pounds)?\b", re.I), None),
]

_DOSE = r"\d+(?:\.\d+)?(?:\s?[-/]\s?\d+(?:\.\d+)?)?\s?(?:mg|mcg|µg|ug|g|grams?|units?|iu|meq|ml|%|mg/ml|puffs?|tabs?|tablets?|caps?|drops?|sprays?)"
_FREQ = (r"once daily|twice daily|three times daily|four times daily|every (?:morning|evening|night|day|other day)|"
         r"daily|nightly|at bedtime|qhs|qam|qpm|qd|q\.d\.|bid|b\.i\.d\.|tid|t\.i\.d\.|qid|q\.i\.d\.|prn|as needed|"
         r"weekly|monthly|q\s?\d+\s?(?:h|hr|hrs|hours?)|every \d+ hours?|qod")
_ROUTE = (r"po|by mouth|orally|oral|iv|intravenous(?:ly)?|im|intramuscular|sc|sq|subq|subcutaneous(?:ly)?|sl|"
          r"sublingual|pr|topical(?:ly)?|inhaled|inh|nasal|ophthalmic|transdermal|nebulized")
_FORM = r"tablets?|tabs?|capsules?|caps?|inhaler|solution|patch|cream|ointment|injection|suspension|drops"
_DURATION = r"(?:for|x)\s?\d+\s?(?:days?|weeks?|months?|d|wks?)"
_MED_ATTR = re.compile(
    rf"(?<![A-Za-z0-9])(?:(?P<dose>{_DOSE})|(?P<frequency>{_FREQ})|(?P<route>{_ROUTE})|(?P<form>{_FORM})|"
    rf"(?P<duration>{_DURATION}))(?![A-Za-z0-9])", re.I)
_BULLET = re.compile(r"^\s*(?:(?:[-*•·]|\d{1,2}[.)])\s*)?")
_MED_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9\-/'.]*(?:\s+[A-Za-z][A-Za-z0-9\-/'.]*){0,2}$")
_MED_LEAD_STOP = {"continue", "start", "started", "stop", "stopped", "take", "takes", "taking", "on", "patient", "pt",
                  "and", "with", "of", "the", "resume", "hold", "increase", "decrease", "discontinue", "new", "restart"}
_MED_LINE_STOP = {"none", "n/a", "na", "see", "see above", "as above", "unchanged", "no changes", "continue",
                  "medications", "medication", "meds", "list", "same", "nkda", "none listed", "reviewed",
                  "continue current medications", "current medications"}
NKDA = re.compile(r"\b(?:NKDA|NKA|NKFA|NKMA|no known (?:drug |food |medication )?allerg(?:y|ies))\b", re.I)
_ALLERGY_ITEM = re.compile(r"\s*(?P<sub>[A-Za-z][A-Za-z0-9\-/' ]*?)\s*(?:\((?P<rx>[^)]*)\)|\s*[-–:]\s*(?P<rx2>.*?))?\s*$")
_REACTION_AFTER = re.compile(r"[ \t]*\((?P<rx>[^)\n]*)\)")

_FOLLOWUP = re.compile(r"\b(?:follow[\s-]?up|f/u|return(?:s|ed)?(?: to| for)?|recheck|re-?evaluate)\b", re.I)
_WHEN = re.compile(r"\b(?:in|within|after)\s+(?P<when>(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a)"
                   r"\s*(?:-\s*\d+\s*)?(?:days?|weeks?|months?|years?|wks?|mos?))\b|\bon\s+(?P<date><DATE_TIME_\d+>)", re.I)
_WITH = re.compile(r"\bwith\s+(?P<with>(?:Dr\.?\s*)?(?:<PERSON_\d+>|[A-Za-z][A-Za-z ]{1,40}?))(?=\s+(?:in|within|on|after)\b|[.,;\n]|$)", re.I)
_REFERRAL = re.compile(r"\b(?:refer(?:red|ral)?|consult(?:ed|ation)?)\s+(?:to\s+)?(?P<to>[A-Za-z][A-Za-z /\-]{2,40}?)"
                       r"(?=[.,;\n]|\s+(?:for|in|on)\b|$)", re.I)
_FAMILY_PHRASES = [
    re.compile(r"\bfamily (?:history|hx) of\s+(?P<x>[^.\n;]+)", re.I),
    re.compile(r"\bFHx?\s*:?\s+(?:of\s+)?(?P<x>[^.\n;]+)", re.I),
    re.compile(r"\b(?:father|mother|brother|sister|parents?|grandmother|grandfather|grandparents?|siblings?|sons?|"
               r"daughters?|aunts?|uncles?)\s+(?:with|has|had|have|died of|diagnosed with|dx'?d with|hx of|history of|"
               r"who had|w/)\s+(?P<x>[^.\n;]+)", re.I),
]
_FAMILY_LINE = re.compile(r"^\s*(?:[-*•·]\s*)?(?:father|mother|brother|sister|parents?|grandmother|grandfather|"
                          r"grandparents?|siblings?|sons?|daughters?|aunts?|uncles?|maternal \w+|paternal \w+)\s*[:\-–]\s*(?P<x>.+)$", re.I)
_ITEM_SPLIT = re.compile(r"\s*(?:,|;|\band\b|/)\s*", re.I)
_ITEM_TAIL = re.compile(r"\s+(?:at|in|age|aged|dx|diagnosed|since|during)\b.*$", re.I)
_NEG_CUE = re.compile(r"^(?:no evidence (?:of|for)|no signs? of|no history of|negative for|absence of|denies|denied|"
                      r"deny|no|not|without|absent|r/o|rule out|ruled out)\s+", re.I)
_SENT_BULLET = re.compile(r"^(?:[-*•·]|\d{1,2}[.)])$")

_MED7_ATTR = {"STRENGTH": "dose", "DOSAGE": "dosage", "FORM": "form", "ROUTE": "route", "FREQUENCY": "frequency",
              "DURATION": "duration"}

# ----------------------------------------------------------------------------- LLM layer
LLM_SYSTEM = (
    "You extract clinical facts from de-identified clinical note excerpts into JSON. Copy `text` VERBATIM "
    "from the excerpt, character for character. Placeholders such as <PERSON_1> or <DATE_TIME_2> are "
    "intentional; never replace, expand or invent them. Only report what is written; do not infer. "
    "`name` is the canonical drug, condition, test or substance name. Leave unknown fields null.")
LLM_SCHEMA = {
    "name": "clinical_facts", "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False, "required": ["facts"],
        "properties": {"facts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["kind", "text", "name"],
            "properties": {
                "kind": {"type": "string", "enum": list(KINDS)},
                "text": {"type": "string"}, "name": {"type": "string"},
                "dose": {"type": ["string", "null"]}, "frequency": {"type": ["string", "null"]},
                "route": {"type": ["string", "null"]}, "value": {"type": ["string", "null"]},
                "unit": {"type": ["string", "null"]}, "reaction": {"type": ["string", "null"]},
            }}}}}}
_LLM_ATTRS = ("dose", "frequency", "route", "value", "unit", "reaction")

_models: _Models | None = None
_lock = threading.Lock()
_run_lock = threading.Lock()          # spaCy pipelines are not safe to share across threads


def _log(msg: str) -> None:
    print(f"[annotate] {msg}", flush=True)


# ----------------------------------------------------------------------------- model loading
def _single_token_placeholders(nlp) -> None:
    """medspaCy's (and spaCy's) tokenizers split '<PERSON_1>' into 5 tokens; keep it whole."""
    old = nlp.tokenizer.token_match
    nlp.tokenizer.token_match = lambda s: PLACEHOLDER.match(s) or (old(s) if old else None)


def _build() -> _Models:
    import medspacy                                    # registers the medspacy_* factories
    import spacy
    from medspacy.section_detection import SectionRule

    host = medspacy.load(medspacy_enable=["medspacy_tokenizer", "medspacy_pyrush", "medspacy_context"])
    _single_token_placeholders(host)
    sec = host.add_pipe("medspacy_sectionizer", config={"rules": None, "apply_sentence_boundary": True})
    shipped = [r for r in SectionRule.from_json(sec.DEFAULT_RULES_FILEPATH)
               if r.literal.lower() not in _DROP_DEFAULT_LITERALS]
    sec.add(shipped)
    sec.add([SectionRule(f"header:{cat}", cat, pattern=_header_regex(names)) for cat, names in SECTION_HEADERS.items()])
    # One token-pattern rule: medspaCy's matcher warns (W036) on every page when its spaCy Matcher
    # holds no patterns at all, and a signature block does end the clinical content.
    sec.add([SectionRule("electronically signed", "signature",
                         pattern=[{"LOWER": {"IN": ["electronically", "digitally"]}}, {"LOWER": "signed"}])])
    sec.assertion_attributes_mapping = {k: dict(v) for k, v in SECTION_ATTRS.items()}

    med7 = spacy.load("en_core_med7_lg")
    _single_token_placeholders(med7)
    bc5 = spacy.load("en_ner_bc5cdr_md", exclude=["tagger", "attribute_ruler", "lemmatizer", "parser"])
    _single_token_placeholders(bc5)
    return _Models(host, med7, bc5)


def load_models() -> _Models:
    """Lazy, thread-safe singleton (same shape as deid.analyzer())."""
    global _models
    if _models is None:
        with _lock:
            if _models is None:
                t0 = time.time()
                _models = _build()
                _log(f"models loaded in {time.time() - t0:.1f}s")
    return _models


def llm_enabled_by_env() -> bool:
    return (os.environ.get("ANNOTATE_LLM") or "0").strip() == "1"


# ----------------------------------------------------------------------------- helpers
def _norm(s: str) -> str:
    return _WS.sub(" ", (s or "").strip().strip(".,;:")).strip().lower()


def _clean(s: str) -> str:
    return _WS.sub(" ", (s or "").strip())


def _canon_lab(name: str) -> str:
    for rx, canon in _LAB_CANON:
        if rx.match(name):
            return canon
    return _norm(name)


def _space_dose(d: str) -> str:
    return _clean(re.sub(r"(\d)(?=[A-Za-zµ%])", r"\1 ", d))


def _iter_lines(text: str, start: int, end: int):
    pos = start
    while pos < end:
        nl = text.find("\n", pos, end)
        le = end if nl < 0 else nl
        yield pos, le
        pos = le + 1


def _line_bounds(text: str, pos: int) -> tuple[int, int]:
    ls = text.rfind("\n", 0, pos) + 1
    le = text.find("\n", pos)
    return ls, (len(text) if le < 0 else le)


def _section_at(sections: list[_Section], pos: int) -> str | None:
    for s in sections:
        if s.title_start <= pos < s.body_end:
            return s.category
    return None


def _nearest_date(text: str, start: int, end: int) -> str | None:
    best, best_d = None, None
    for m in DATE_TOKEN.finditer(text):
        d = max(0, m.start() - end, start - m.end())
        if best_d is None or d < best_d:
            best, best_d = m.group(0), d
    return best


def _split_items(s: str):
    """Yield (offset, item) for comma/and-separated items, ignoring separators inside parentheses."""
    depth, cur, out = 0, 0, []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0:
            m = _ITEM_SPLIT.match(s, i)
            if m and m.end() > i and (i > 0):
                out.append((cur, s[cur:i]))
                i = m.end(); cur = i
                continue
        i += 1
    out.append((cur, s[cur:]))
    for off, item in out:
        lead = len(item) - len(item.lstrip())
        item = item.strip()
        if item:
            yield off + lead, item


def _sections_of(doc, text: str) -> list[_Section]:
    n = len(doc)

    def ch(i: int) -> int:
        return doc[i].idx if i < n else len(text)

    out = []
    for s in doc._.sections:
        cat = _SECTION_ALIAS.get(s.category, s.category) if s.category else None
        out.append(_Section(cat, ch(s.title_start), ch(s.body_start), ch(s.body_end)))
    return out


def _line_sentences(doc) -> None:
    """PyRuSH runs list items and headers together into one sentence; ConText scopes cues by
    sentence, so '- no evidence of pneumonia\\n- COPD' would negate COPD.  Start a new sentence
    after a newline when the next line is a bullet, the previous line ended a clause, or the
    newline is a blank line.  Wrapped prose (no such cue) is left alone."""
    for i in range(1, len(doc) - 1):
        tok = doc[i]
        if "\n" not in tok.text:
            continue
        prev, nxt = doc[i - 1], doc[i + 1]
        if (tok.text.count("\n") > 1 or _SENT_BULLET.match(nxt.text) or prev.text[-1:] in ".:;"):
            nxt.is_sent_start = True


# ----------------------------------------------------------------------------- rules layer
def _rules(text: str, sections: list[_Section], sents: list[tuple[int, int]]) -> list[_Cand]:
    out: list[_Cand] = []
    for m in LAB_RE.finditer(text):
        attrs = {"value": m.group("value")}
        if m.group("unit"):
            attrs["unit"] = m.group("unit")
        out.append(_Cand(m.start(), m.end(), "lab", attrs, "rules", normalized=_canon_lab(m.group("name"))))
    for canon, rx, unit in VITAL_RES:
        for m in rx.finditer(text):
            attrs = {"value": re.sub(r"\s+", "", m.group("value"))}
            u = (m.groupdict().get("unit") or unit)
            if u:
                attrs["unit"] = _clean(u.replace(" ", ""))
            out.append(_Cand(m.start(), m.end(), "vital", attrs, "rules", normalized=canon))
    for sec in sections:
        if sec.category == "allergy":
            out += _allergy_rules(text, sec)
        elif sec.category == "medications":
            out += _med_line_rules(text, sec)
        elif sec.category in ("observation_and_plan", "hospital_course", "patient_instructions"):
            out += _plan_rules(text, sec, sents)
        elif sec.category == "family_history":
            out += _family_section_rules(text, sec)
        elif sec.category in ("diagnoses", "problem_list"):
            out += _dx_line_rules(text, sec)
    out += _family_phrase_rules(text)
    return out


_DX_LINE_STOP = {"none", "n/a", "see below", "as above", "deferred", "same", "unchanged"}


def _dx_line_rules(text: str, sec: _Section) -> list[_Cand]:
    """A diagnosis/problem list is a list of problems: each short list line is one problem, whole
    (the NER model clips 'type 2 diabetes mellitus' to 'diabetes mellitus'). Prose lines, 'label:
    value' lines and anything with a number-value pattern are left to the NER and lab rules.
    A leading negation cue is trimmed off the span but stays in the sentence for ConText."""
    out = []
    for ls, le in _iter_lines(text, sec.body_start, sec.body_end):
        line = text[ls:le]
        off = _BULLET.match(line).end()
        core = line[off:].rstrip()
        if not core.strip() or PLACEHOLDER.search(core) or core.strip().lower() in _DX_LINE_STOP:
            continue
        if ". " in core or ":" in core or len(core.split()) > 8:
            continue
        if LAB_RE.search(core) or any(rx.search(core) for _, rx, _ in VITAL_RES) or _MED_ATTR.search(core):
            continue
        s, e = _trim_problem(text, ls + off, ls + off + len(core))
        if s < e and re.search(r"[A-Za-z]", text[s:e]):
            out.append(_Cand(s, e, "problem", {}, "rules", normalized=_norm(text[s:e])))
    return out


def _allergy_rules(text: str, sec: _Section) -> list[_Cand]:
    out = []
    for ls, le in _iter_lines(text, sec.body_start, sec.body_end):
        line = text[ls:le]
        if not line.strip() or NKDA.search(line):
            continue
        off = _BULLET.match(line).end()
        for item_off, item in _split_items(line[off:]):
            m = _ALLERGY_ITEM.match(item)
            if not m:
                continue
            sub = m.group("sub").strip()
            if not sub or PLACEHOLDER.search(sub) or len(sub.split()) > 4 or sub.lower() in _MED_LINE_STOP:
                continue
            reaction = _clean(m.group("rx") or m.group("rx2") or "") or None
            s = ls + off + item_off + m.start("sub")
            attrs = {"reaction": reaction} if reaction else {}
            out.append(_Cand(s, s + len(sub), "allergy", attrs, "rules", normalized=_norm(sub)))
    return out


def _med_line(line: str) -> tuple[int, int, str, dict] | None:
    """Parse 'name [dose] [form] [route] [frequency] [duration]' from one medication-list line.
    Returns (start, end, name, attributes) relative to the line, or None."""
    off = _BULLET.match(line).end()
    core = line[off:].rstrip()
    if not core.strip() or NKDA.search(core) or PLACEHOLDER.search(core):
        return None
    attrs, first, last = {}, None, None
    for m in _MED_ATTR.finditer(core):
        key = m.lastgroup
        val = _clean(m.group(key))
        if key == "dose":
            val = _space_dose(val)
        attrs.setdefault(key, val)
        first = m.start() if first is None else first
        last = m.end()
    name = core[:first] if first is not None else core
    name = name.strip(" ,:;-(")
    words = name.split()
    while words and words[0].lower() in _MED_LEAD_STOP:
        words = words[1:]
    name = " ".join(words)
    if not name or not _MED_NAME.match(name) or name.lower() in _MED_LINE_STOP:
        return None
    if first is None and len(words) > 3:
        return None
    name_start = off + core.find(name)
    end = off + (last if last is not None else name_start - off + len(name))
    return name_start, end, name, attrs


def _med_line_rules(text: str, sec: _Section) -> list[_Cand]:
    out = []
    for ls, le in _iter_lines(text, sec.body_start, sec.body_end):
        parsed = _med_line(text[ls:le])
        if parsed is None:
            continue
        s, e, name, attrs = parsed
        out.append(_Cand(ls + s, ls + e, "medication", attrs, "rules", normalized=_norm(name)))
    return out


def _plan_rules(text: str, sec: _Section, sents: list[tuple[int, int]]) -> list[_Cand]:
    out = []
    for s, e in sents:
        s, e = max(s, sec.body_start), min(e, sec.body_end)
        if s >= e:
            continue
        seg = text[s:e]
        lead = len(seg) - len(seg.lstrip())
        s, seg = s + lead, seg.strip()
        if not seg or len(seg) > 400:
            continue
        if _FOLLOWUP.search(seg):
            attrs = {}
            w = _WHEN.search(seg)
            if w:
                attrs["when"] = _clean(w.group("when") or w.group("date"))
            with_ = _WITH.search(seg)
            if with_:
                attrs["with"] = _clean(with_.group("with"))
            out.append(_Cand(s, s + len(seg), "plan", attrs, "rules", normalized=_norm(seg), as_entity=False))
        r = _REFERRAL.search(seg)
        if r:
            out.append(_Cand(s, s + len(seg), "referral", {"to": _norm(r.group("to"))}, "rules",
                             normalized=_norm(seg), as_entity=False))
    return out


def _family_items(text: str, x_start: int, x: str) -> list[_Cand]:
    out = []
    for off, item in _split_items(x):
        item_clean = _ITEM_TAIL.sub("", item).strip(" .,;:")
        item_clean = re.sub(r"^(?:a|an|the|of)\s+", "", item_clean, flags=re.I)
        if not item_clean or PLACEHOLDER.search(item_clean) or len(item_clean.split()) > 6:
            continue
        s = x_start + off + item.find(item_clean)
        if s < x_start:
            continue
        out.append(_Cand(s, s + len(item_clean), "problem", {}, "rules", normalized=_norm(item_clean),
                         fixed_assertion="family"))
    return out


def _family_phrase_rules(text: str) -> list[_Cand]:
    out = []
    for rx in _FAMILY_PHRASES:
        for m in rx.finditer(text):
            out += _family_items(text, m.start("x"), m.group("x"))
    return out


def _family_section_rules(text: str, sec: _Section) -> list[_Cand]:
    out = []
    for ls, le in _iter_lines(text, sec.body_start, sec.body_end):
        m = _FAMILY_LINE.match(text[ls:le])
        if m:
            out += _family_items(text, ls + m.start("x"), m.group("x"))
    return out


# ----------------------------------------------------------------------------- NER layer
def _trim_problem(text: str, s: int, e: int) -> tuple[int, int]:
    """bc5cdr emits 'Denies chest pain' as one span; drop the leading cue so ConText can see it,
    and shed surrounding punctuation."""
    m = _NEG_CUE.match(text[s:e])
    if m:
        s += m.end()
    while s < e and text[s] in " \t(":
        s += 1
    while e > s and text[e - 1] in " \t.,;:)":
        e -= 1
    return s, e


def _ner(text: str, models: _Models) -> list[_Cand]:
    out: list[_Cand] = []
    ents = list(models.med7(text).ents)
    for i, e in enumerate(ents):
        if e.label_ != "DRUG":
            continue
        attrs = {}
        for f in ents[i + 1:]:
            if f.label_ == "DRUG" or "\n" in text[e.end_char:f.start_char]:
                break                                          # attributes bind to the nearest DRUG on the line
            key = _MED7_ATTR.get(f.label_)
            if key:
                attrs.setdefault(key, _space_dose(f.text) if key == "dose" else _clean(f.text))
        out.append(_Cand(e.start_char, e.end_char, "medication", attrs, "med7", normalized=_norm(e.text)))
    for e in models.bc5cdr(text).ents:
        if e.label_ != "DISEASE":
            continue                                           # CHEMICAL: Med7 owns drugs
        s, t = _trim_problem(text, e.start_char, e.end_char)
        if s < t:
            out.append(_Cand(s, t, "problem", {}, "bc5cdr"))
    return out


# ----------------------------------------------------------------------------- LLM layer
def _llm_layer(text: str, sections: list[_Section], cands: list[_Cand], usage: dict | None) -> list[_Cand]:
    bodies = [text[s.body_start:s.body_end].strip() for s in sections if s.category in LLM_SECTIONS]
    sent = "\n\n".join(b for b in bodies if b)
    if not sent:
        return cands
    try:
        obj, used = llm.extract_json("small", LLM_SYSTEM, sent, LLM_SCHEMA, max_tokens=1500)
    except Exception as e:                                     # the LLM is optional; never fail the page
        _log(f"llm layer failed: {type(e).__name__}")
        return cands
    if usage is not None:
        usage["small"] = usage.get("small", 0) + used
    if not isinstance(obj, dict) or not isinstance(obj.get("facts"), list):
        _log("llm layer: no parsable facts")
        return cands
    if deid.contains_phi(json.dumps(obj)):
        _log("llm layer: output failed the PHI check; dropped")
        return cands
    added = filled = dropped = 0
    for item in obj["facts"]:
        if not isinstance(item, dict):
            continue
        kind, txt = item.get("kind"), item.get("text")
        if kind not in KINDS or not isinstance(txt, str) or not txt.strip() or txt not in sent:
            dropped += 1
            continue                                           # not verbatim -> invented or paraphrased
        pos = text.find(txt)
        if pos < 0:
            dropped += 1
            continue
        attrs = {k: _clean(item[k]) for k in _LLM_ATTRS if isinstance(item.get(k), str) and item[k].strip()}
        if "dose" in attrs:
            attrs["dose"] = _space_dose(attrs["dose"])
        name = _norm(item.get("name") or txt) or _norm(txt)
        match = next((c for c in cands if c.source != "llm" and c.kind == kind
                      and (c.normalized or _norm(text[c.start:c.end])) == name), None)
        if match is not None:
            for k, v in attrs.items():
                if k not in match.attributes:
                    match.attributes[k] = v
                    filled += 1
            continue
        cands.append(_Cand(pos, pos + len(txt), kind, attrs, "llm", normalized=name,
                           as_entity=kind not in ("plan", "referral", "other")))
        added += 1
    _log(f"llm layer: {added} added, {filled} attributes filled, {dropped} dropped")
    return cands


# ----------------------------------------------------------------------------- merge
def _reaction_after(text: str, end: int) -> dict:
    _, le = _line_bounds(text, end)
    m = _REACTION_AFTER.match(text, end, le)
    return {"reaction": _clean(m.group("rx"))} if m and m.group("rx").strip() else {}


def _merge(text: str, cands: list[_Cand], sections: list[_Section]) -> list[_Cand]:
    holes = [(m.start(), m.end()) for m in PLACEHOLDER.finditer(text)]
    keep: list[_Cand] = []
    for c in cands:
        if c.start >= c.end:
            continue
        if c.as_entity and any(s < c.end and c.start < e for s, e in holes):
            continue                                           # a placeholder is never an entity
        surface = text[c.start:c.end]
        if not re.search(r"[A-Za-z0-9]", surface):
            continue
        if _section_at(sections, c.start) == "allergy":
            if c.kind == "medication":
                ls, le = _line_bounds(text, c.start)
                if NKDA.search(text[ls:le]):
                    continue
                c = replace(c, kind="allergy", attributes={**_reaction_after(text, c.end), **c.attributes},
                            normalized=c.normalized or _norm(surface))
            elif c.kind == "problem":
                continue                                       # a DISEASE in the allergy list is a reaction
        keep.append(c)
    keep.sort(key=lambda c: (-PRIORITY[c.source], -(c.end - c.start), c.start))
    accepted: list[_Cand] = []
    for c in keep:
        hit = next((a for a in accepted if a.start < c.end and c.start < a.end and a.as_entity == c.as_entity), None)
        if hit is None:
            accepted.append(c)
        elif hit.kind == c.kind:                               # lower layer fills what the winner lacks
            for k, v in c.attributes.items():
                hit.attributes.setdefault(k, v)
    return sorted(accepted, key=lambda c: (c.start, c.end))


def _assertion(span) -> str:
    if span._.is_family:
        return "family"
    if span._.is_historical:
        return "historical"
    if span._.is_negated:
        return "absent"
    if span._.is_uncertain:
        return "possible"
    if span._.is_hypothetical:
        return "conditional"
    return "present"


# ----------------------------------------------------------------------------- public API
def page_sections(text: str) -> list[tuple[str | None, int, int, int]]:
    """(category, title_start, body_start, body_end) char offsets for a page (diagnostics/tests)."""
    m = load_models()
    with _run_lock:
        doc = m.host.make_doc(text)
        doc = m.host.get_pipe("medspacy_pyrush")(doc)
        doc = m.host.get_pipe("medspacy_sectionizer")(doc)
        return [(s.category, s.title_start, s.body_start, s.body_end) for s in _sections_of(doc, text)]


def annotate_page(text: str, page: int, *, llm_enabled: bool | None = None, usage: dict | None = None) -> list[Fact]:
    if not text or not text.strip():
        return []
    m = load_models()
    use_llm = llm_enabled_by_env() if llm_enabled is None else llm_enabled
    with _run_lock:
        host = m.host
        doc = host.make_doc(text)
        doc = host.get_pipe("medspacy_pyrush")(doc)
        _line_sentences(doc)
        sec = host.get_pipe("medspacy_sectionizer")
        doc = sec(doc)                                         # sections + header sentence boundaries
        sections = _sections_of(doc, text)
        sents = [(s.start_char, s.end_char) for s in doc.sents]
        cands = _rules(text, sections, sents) + _ner(text, m)
        if use_llm:
            cands = _llm_layer(text, sections, cands, usage)
        cands = _merge(text, cands, sections)

        from spacy.util import filter_spans
        by_span: dict[tuple[int, int], _Cand] = {}
        direct: list[_Cand] = []
        for c in cands:
            sp = doc.char_span(c.start, c.end, label=c.kind.upper(), alignment_mode="expand") if c.as_entity else None
            if sp is None:
                direct.append(c)
            else:
                by_span.setdefault((sp.start_char, sp.end_char), (sp, c))
        spans = filter_spans([sp for sp, _ in by_span.values()])
        doc.set_ents(spans)
        doc = host.get_pipe("medspacy_context")(doc)
        sec.set_assertion_attributes(doc.ents)

        facts: list[Fact] = []
        for ent in doc.ents:
            _, c = by_span[(ent.start_char, ent.end_char)]
            facts.append(_fact(text, page, ent.start_char, ent.end_char, c,
                               c.fixed_assertion or _assertion(ent), _SECTION_ALIAS.get(ent._.section_category, ent._.section_category)))
        for c in direct:
            facts.append(_fact(text, page, c.start, c.end, c, c.fixed_assertion or "present", _section_at(sections, c.start)))
    facts.sort(key=lambda f: (f.start, f.end, f.kind))
    return facts


def _fact(text: str, page: int, s: int, e: int, c: _Cand, assertion: str, section: str | None) -> Fact:
    surface = text[s:e]
    return Fact(page=page, start=s, end=e, kind=c.kind, text=surface,
                normalized=c.normalized or _norm(surface), attributes=dict(c.attributes),
                assertion=assertion if assertion in ASSERTIONS else "present", section=section,
                date_token=_nearest_date(text, s, e), confidence=CONFIDENCE[c.source], extractor=EXTRACTOR[c.source])


def annotate_pages(texts: list[str], *, llm_enabled: bool | None = None, usage: dict | None = None) -> list[list[Fact]]:
    """texts are DE-IDENTIFIED page strings (1-based page numbers follow list order).  Returns one
    fact list per page.  `usage`, if given, accumulates LLM tokens under 'small'."""
    t0 = time.time()
    out = [annotate_page(t, i + 1, llm_enabled=llm_enabled, usage=usage) for i, t in enumerate(texts)]
    if texts:
        ms = (time.time() - t0) * 1000
        _log(f"{len(texts)} page(s), {sum(len(f) for f in out)} facts, {ms / len(texts):.0f} ms/page")
    return out


def counts_by_kind(facts: list[list[Fact]] | list[list[dict]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for page in facts or []:
        for f in page:
            k = f["kind"] if isinstance(f, dict) else f.kind
            out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))
