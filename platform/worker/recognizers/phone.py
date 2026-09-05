"""NANP phone numbers with country code and extension.

Problem. Presidio's PhoneRecognizer (python-phonenumbers) misses common chart formats:
``+1-921-899-3518x19093`` and ``(555) 201-8842 ext. 12`` survived the first end-to-end run
(CHANGELOG 2026-09-03), and a bare ten-digit number after ``Tel:`` was only caught because
spaCy had mislabelled it as a date, which the dosing-frequency date filter would have let
through. This is a regex backstop, not a replacement: both recognizers run and the caller
resolves overlapping spans.

Scores. ``nanp_with_ext`` 0.6: optional ``+1`` / ``1`` prefix, area code with or without
parentheses, ``-`` / ``.`` / space separators, optional ``x`` / ``ext.`` / ``extension`` and
1-6 digits. ``nanp_bare`` 0.35 for an unformatted ten-digit run of valid NANP shape
(``Tel: 9218993518``): below the 0.5 threshold alone, lifted to 0.7 by Presidio's context
enhancer when ``phone``, ``tel``, ``telephone``, ``cell``, ``mobile``, ``fax`` or ``call``
appears in the words before it.

Examples (tests/test_recognizers.py). ``+1-921-899-3518x19093``, ``(555) 201-8842 ext. 12``,
``555.201.8842``, ``921-899-3518 extension 7`` and ``+1 921 899 3518`` are each one
PHONE_NUMBER span that includes the extension; ``Tel: 9218993518 for records.`` is one span.
"""
from presidio_analyzer import Pattern, PatternRecognizer

NAME = "phone_regex"
CONTEXT = ["phone", "tel", "telephone", "cell", "mobile", "fax", "call"]


def phone_recognizer() -> PatternRecognizer:
    nanp = r"(?:\+?1[-. ])?(?:\(\d{3}\)\s?|\d{3}[-. ])\d{3}[-. ]\d{4}(?:\s*(?:x|ext\.?|extension)\s*\d{1,6})?"
    # A bare 10-digit run (Tel: 9218993518) is only a phone number when a phone-ish word is
    # nearby: 0.35 alone (below the 0.5 threshold), lifted by the context enhancer when
    # 'tel'/'phone'/'fax'... appears in the surrounding words.
    bare = r"\b(?:1[-. ]?)?[2-9]\d{2}[2-9]\d{6}\b"
    return PatternRecognizer(supported_entity="PHONE_NUMBER", name=NAME,
                             patterns=[Pattern("nanp_with_ext", nanp, 0.6), Pattern("nanp_bare", bare, 0.35)],
                             context=CONTEXT)
