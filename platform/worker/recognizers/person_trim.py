"""Trim titles and field labels off PERSON spans.

Problem. spaCy tags a bare ``Dr`` as a PERSON often enough that charts came out as
``Attending: <PERSON_2>. <PERSON_1>`` with ``<PERSON_2>`` = ``Dr``, and the model then
answered "the attending physician is Dr." with the title as the name (CHANGELOG 2026-09-04).
A span that runs into the next field (``Joshua Duncan DOB``) puts the label into the PHI map
and the re-identified answer.

Rule. A PERSON span whose every word is a title or a label is dropped. Otherwise leading
titles (``Dr``, ``Mrs``, ``Attending``, ...) and trailing labels (``DOB``, ``MRN``, ``Date``,
...) are stripped, together with the punctuation and spaces between them and the name.
Words are split on whitespace and ``.,:;``; the comparison is case-insensitive.

Like ``date_filter`` this is a result filter the caller applies after analysis; upstream it
belongs in ``SpacyRecognizer`` as a post-processing step (docs/UPSTREAM.md).

Examples (tests/test_recognizers.py). ``Patient: Joshua Duncan DOB: 1975`` span [9, 26)
-> [9, 22) ``Joshua Duncan``; ``Seen by Dr Young today`` [8, 16) -> [11, 16) ``Young``;
``Attending: Dr.`` [11, 14) -> None; ``Plan`` [0, 4) -> None.
"""
import re

# Titles and field labels are not identifiers. A span whose whole text is a title or label is
# dropped; a PERSON span that starts with a title or ends with a label ("Dr Young",
# "Joshua Duncan DOB") is trimmed to the name.
TITLES = {"dr", "doctor", "mr", "mrs", "ms", "miss", "mx", "prof", "professor", "md", "do", "rn", "np", "pa",
          "attending", "physician", "provider", "patient", "resident", "nurse"}
LABELS = {"dob", "mrn", "ssn", "date", "name", "phone", "address", "plan", "attending", "patient",
          "physician", "provider", "diagnoses", "medications", "allergies"}
_WORD_SPLIT = re.compile(r"[\s.,:;]+")


def trim_person(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Return trimmed [start, end) for a PERSON span, or None to drop it entirely."""
    words = [w for w in _WORD_SPLIT.split(text[start:end]) if w]
    if not words:
        return None
    lowered = [w.lower() for w in words]
    if all(w in TITLES or w in LABELS for w in lowered):
        return None
    # leading titles
    while lowered and lowered[0] in TITLES:
        first = words.pop(0); lowered.pop(0)
        start = text.index(first, start) + len(first)
        while start < end and text[start] in " .,:;":
            start += 1
    # trailing labels
    while lowered and lowered[-1] in LABELS:
        last = words.pop(); lowered.pop()
        end = text.rindex(last, start, end)
        while end > start and text[end - 1] in " .,:;":
            end -= 1
    return (start, end) if end > start else None
