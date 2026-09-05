"""Title- and label-anchored clinician / patient names.

Problem. spaCy NER misses ``Dr. <common-word surname>`` often enough to fail the recall
gate: all four PHI survivors of the first eval run were ``Dr. Fields``, ``Dr. Lewis``,
``Dr. Young`` and ``Dr. Holder`` (CHANGELOG 2026-09-03; recall 0.967 against a 0.99 gate,
1.000 after this recognizer). Anchoring on the title or field label finds them without a
model, and the lookbehind keeps the title out of the span so ``Attending: Dr. Young`` becomes
``Attending: Dr. <PERSON_2>``.

Scores. 0.7 for one to three capitalised words (apostrophes and hyphens allowed) after
``Dr. ``, ``Dr ``, ``Doctor ``, ``MD ``, ``Attending: ``, ``Physician: ``, ``Provider: ``,
``Patient: ``, ``Patient Name: `` or ``Name: `` (one fixed-width lookbehind per spelling).
Presidio compiles every pattern with IGNORECASE; the scoped ``(?-i:...)`` flag keeps the
name part case-sensitive so the span stops at the first lowercase word.

Examples (tests/test_recognizers.py). ``Dr. Priya Raghunathan-Okafor reviewed the chart.``
gives ``Priya Raghunathan-Okafor`` (not ``... reviewed``); ``Attending: Priya
Raghunathan-Okafor.`` gives the name; ``Attending: Dr. Hawkins    Date of service:
2026-02-02`` gives ``Hawkins`` only, the title survives.
"""
from presidio_analyzer import Pattern, PatternRecognizer

NAME = "title_name_regex"
ANCHORS = (r"\bDr\. ", r"\bDr ", r"\bDoctor ", r"\bMD ", r"\bAttending: ", r"\bPhysician: ",
           r"\bProvider: ", r"\bPatient: ", r"\bPatient Name: ", r"\bName: ")


def clinician_name_recognizer() -> PatternRecognizer:
    # Presidio compiles patterns with IGNORECASE; (?-i:...) makes the name part case-sensitive so
    # it stops at the first lowercase word ("Dr. Priya Raghunathan-Okafor reviewed" -> the name only).
    name = r"(?-i:[A-Z][a-zA-Z'\-]+(?: [A-Z][a-zA-Z'\-]+){0,2})"
    pats = [Pattern(f"title_{i}", rf"(?<={lb}){name}", 0.7) for i, lb in enumerate(ANCHORS)]
    return PatternRecognizer(supported_entity="PERSON", name=NAME, patterns=pats)
