"""Calendar-date filter for DATE_TIME results: keep dates, drop frequencies and durations.

Problem. spaCy's DATE label also covers dosing frequencies and durations (``daily``,
``nightly``, ``in 2 weeks``, ``tonight``), which are clinical content, not identifiers.
Redacting them destroys dosing instructions: ``sertraline 50 mg <DATE_TIME_2>`` in the index
caused 11 of the 12 medication-list misses in the first eval run (CHANGELOG 2026-09-03;
answer accuracy 0.575 before, 0.95 after this filter and the judge fix). Safe Harbor dates are
dates tied to a person (birth, admission, discharge, death), so a DATE_TIME span is kept only
if it contains something calendar-like.

This is a result filter, not a recognizer. Presidio has no hook for narrowing an NER
recognizer's output, so the caller applies :func:`is_identifying_date` to each DATE_TIME
result after ``AnalyzerEngine.analyze``; upstream, the natural home is an option on
``SpacyRecognizer`` (docs/UPSTREAM.md).

Calendar-like means any of: a month name or abbreviation (``March``, ``Sept.``); a numeric
date ``3/5/2024`` or ``03-05-24``; an ISO date ``2024-03-05``; a four-digit year 1900-2099;
an ordinal day (``5th``). Matching is case-insensitive.

Examples (tests/test_recognizers.py). Kept: ``1985-03-12``, ``03/05/2024``, ``March 9, 2024``.
Dropped: ``daily``, ``nightly``, ``2 weeks``, ``48 hours``, ``2 weeks later``.
"""
import re

# Keep a DATE_TIME hit only if it contains something calendar-like.
DATE_LIKE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\b"     # month names
    r"|\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b"                                     # 3/5/2024, 03-05-24
    r"|\b\d{4}-\d{2}-\d{2}\b"                                                     # ISO
    r"|\b(?:19|20)\d{2}\b"                                                         # a year
    r"|\b\d{1,2}(?:st|nd|rd|th)\b",                                                # 5th (of March)
    re.IGNORECASE)


def is_identifying_date(span: str) -> bool:
    """True if a DATE_TIME span is a Safe Harbor date rather than a frequency or duration."""
    return bool(DATE_LIKE.search(span))
