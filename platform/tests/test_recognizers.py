"""worker/recognizers/* against the real Presidio engine with en_core_web_sm (tests/conftest.py
pins SPACY_MODEL before import). One section per module: package shape, MRN, phone, clinician
name, address, date filter, person trim.

Recognizer-level tests call ``recognizer.analyze`` directly (no NLP artifacts needed for a
PatternRecognizer) and assert exact spans and scores. Pipeline-level tests go through
``deid.scrub`` so the interaction with spaCy, the context enhancer and the Scrubber's overlap
resolution is covered. Scrubber/restore/contains_phi behaviour lives in test_deid.py."""
import ast
import pathlib
import sys

import pytest

from worker import deid
from worker.recognizers import (address, clinician_name, custom_recognizers, date_filter, mrn,
                                person_trim, phone)
from worker.recognizers.date_filter import is_identifying_date
from worker.recognizers.person_trim import trim_person

from test_deid import assert_well_formed

PACKAGE = pathlib.Path(deid.__file__).parent / "recognizers"


def spans(recognizer, text, entity):
    """(text, score) of each hit from one recognizer on its own, in text order."""
    hits = recognizer.analyze(text, [entity])
    return [(text[h.start:h.end], round(h.score, 2)) for h in sorted(hits, key=lambda h: h.start)]


# ---------------------------------------------------------------- package shape

def test_custom_recognizers_order_names_and_entities():
    recs = custom_recognizers()
    assert [(r.name, r.supported_entities[0]) for r in recs] == [
        ("mrn_regex", "MRN"), ("phone_regex", "PHONE_NUMBER"),
        ("title_name_regex", "PERSON"), ("street_address_regex", "LOCATION")]
    assert custom_recognizers()[0] is not recs[0]                     # fresh instances each call
    registered = {r.name for r in deid.analyzer().registry.recognizers}
    assert {r.name for r in recs} <= registered


@pytest.mark.parametrize("module", sorted(p.name for p in PACKAGE.glob("*.py")))
def test_modules_depend_only_on_presidio(module):
    """Each module must be liftable into Presidio unchanged: no worker.* imports, and only
    __init__ may use relative imports (of its siblings)."""
    tree = ast.parse((PACKAGE / module).read_text())
    allowed = set(sys.stdlib_module_names) | {"presidio_analyzer"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("worker"), (module, alias.name)
                assert alias.name.split(".")[0] in allowed, (module, alias.name)
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("worker"), (module, node.module)
            if node.level:
                assert module == "__init__.py", (module, "relative import outside __init__")
            else:
                assert node.module.split(".")[0] in allowed, (module, node.module)


# ---------------------------------------------------------------- mrn

@pytest.mark.parametrize("text", ["MRN: 1234567", "MRN:1234567", "MRN 1234567",
                                  "MRN# 1234567", "MRN#1234567", "MRN: 1234567890"])
def test_labeled_mrn_forms(text):
    clean, phi_map = deid.scrub(text)
    digits = text.split("MRN")[1].lstrip(":# ")
    assert digits not in clean
    assert clean.startswith("MRN")                     # the label is kept, only digits replaced
    assert phi_map == {"<MRN_1>": digits}


def test_mrn_recognizer_scores_labelled_high_and_bare_low():
    r = mrn.mrn_recognizer()
    assert spans(r, "MRN: 1234567", "MRN") == [("1234567", 0.85)]
    assert spans(r, "chart 1234567", "MRN") == [("1234567", 0.3)]      # below threshold alone
    assert spans(r, "12345", "MRN") == []                               # too short


def test_label_variants_are_one_edit_or_spacing_only():
    def edits(a, b):                                             # Levenshtein, small strings
        d = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            prev, d[0] = d[0], i
            for j, cb in enumerate(b, 1):
                prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
        return d[-1]
    vs = mrn.label_variants("MRN")
    assert {"MAN", "MRM", "RN", "MR", "MN", "M R N", "M RN", "MR N"} <= vs
    assert "MRN" not in vs and "MRNN" not in vs and "MRN " not in vs      # no exact, no insertions
    assert len(vs) == 75 + 3 + 3
    assert all(edits(v.replace(" ", ""), "MRN") <= 1 for v in vs)


@pytest.mark.parametrize("text, label", [("MAN: 1234567", "MAN:"), ("MRM 1234567", "MRM"),
                                         ("M R N: 1234567", "M R N:"), ("mrn# 1234567", "mrn#")])
def test_ocr_damaged_mrn_label_still_anchors(text, label):
    r = mrn.mrn_recognizer()
    score = 0.85 if label.upper().startswith("MRN") else 0.7
    assert spans(r, text, "MRN") == [("1234567", score)]
    clean, phi_map = deid.scrub(text)
    assert "1234567" not in clean
    assert phi_map.get("<MRN_1>") == "1234567"
    assert label in deid.restore(clean, phi_map)


def test_bare_digit_run_on_demographics_line_is_an_mrn():
    line = "Patient: John Doe   1234567   DOB 01/02/1960"
    assert spans(mrn.mrn_recognizer(), line, "MRN") == [("1234567", 0.5)]
    clean, phi_map = deid.scrub(line)
    assert "1234567" not in clean and "John Doe" not in clean and "01/02/1960" not in clean
    assert_well_formed(clean, phi_map)
    assert deid.restore(clean, phi_map) == line


def test_demographics_cue_must_be_on_the_same_line():
    r = mrn.mrn_recognizer()
    assert spans(r, "Patient: John Doe\nAccount 1234567", "MRN") == [("1234567", 0.3)]   # bare only
    assert spans(r, "Account 1234567\nSex: F", "MRN") == [("1234567", 0.3)]
    assert spans(r, "Age 64   1234567", "MRN") == [("1234567", 0.5)]


@pytest.mark.parametrize("tail, kept", [
    ("DOB 03/05/2024", None),            # a date: no six-digit run
    ("Phone 555-0100", "555-0100"),      # a local phone number
    ("Kingland, TX 75001", None),        # a ZIP: five digits
    ("WBC 11000", "WBC 11000"),          # a five-digit lab value
    ("HbA1c 9.0", "HbA1c 9.0"),          # a lab value with a decimal
])
def test_demographics_fallback_ignores_dates_phones_zips_and_labs(tail, kept):
    line = f"Patient: John Doe   {tail}"
    assert spans(mrn.mrn_recognizer(), line, "MRN") == []
    clean, phi_map = deid.scrub(line)
    assert "<MRN_" not in clean, clean
    assert all(not t.startswith("<MRN_") for t in phi_map), phi_map
    if kept:
        assert kept in clean, clean


# ---------------------------------------------------------------- phone

@pytest.mark.parametrize("phone_", ["+1-921-899-3518x19093", "(555) 201-8842 ext. 12",
                                    "555.201.8842", "921-899-3518 extension 7", "+1 921 899 3518"])
def test_phone_forms_with_extensions(phone_):
    text = f"Contact phone: {phone_}. Thanks."
    clean, phi_map = deid.scrub(text)
    assert phone_ not in clean
    assert_well_formed(clean, phi_map)
    assert phi_map.get("<PHONE_NUMBER_1>") == phone_
    assert deid.restore(clean, phi_map) == text


def test_phone_recognizer_extension_is_part_of_the_span():
    r = phone.phone_recognizer()
    assert spans(r, "call (555) 201-8842 ext. 12 now", "PHONE_NUMBER") == [("(555) 201-8842 ext. 12", 0.6)]
    assert spans(r, "Tel: 9218993518", "PHONE_NUMBER") == [("9218993518", 0.35)]   # needs context
    assert spans(r, "WBC 11000", "PHONE_NUMBER") == []


# ---------------------------------------------------------------- clinician name

def test_uncommon_hyphenated_name_after_honorific():
    clean, phi_map = deid.scrub("Dr. Priya Raghunathan-Okafor reviewed the chart.")
    assert "Raghunathan" not in clean
    assert "Priya Raghunathan-Okafor" in phi_map.values()


def test_uncommon_name_after_terse_label_is_redacted():
    clean, _ = deid.scrub("Attending: Priya Raghunathan-Okafor.")
    assert "Raghunathan" not in clean


def test_name_recognizer_stops_at_first_lowercase_word_and_keeps_title():
    r = clinician_name.clinician_name_recognizer()
    assert spans(r, "Dr. Priya Raghunathan-Okafor reviewed the chart.", "PERSON") == [("Priya Raghunathan-Okafor", 0.7)]
    # "Dr" is matched after "Attending: " and "Young" after "Dr. "; the bare title is what
    # person_trim removes downstream, the recognizer itself does not know titles from names.
    assert spans(r, "Attending: Dr. Young    Date of service: 2026-04-02", "PERSON") == [("Dr", 0.7), ("Young", 0.7)]
    assert spans(r, "the doctor said", "PERSON") == []


# ---------------------------------------------------------------- address

def test_labelled_address_line_is_fully_redacted():
    text = ("Phone: 555-201-8842    Address: 609 Stacey Roads, New Brendaton, IN 06606\n"
            "Attending: Dr. Young    Date of service: 2026-04-02")
    clean, phi = deid.scrub(text)
    for part in ("609 Stacey Roads", "New Brendaton", "06606", "Young", "555-201-8842", "2026-04-02"):
        assert part not in clean, clean
    assert "Phone: <PHONE_NUMBER_1>" in clean
    assert "Attending: " in clean and "<PERSON_" in clean
    assert "609 Stacey Roads, New Brendaton, IN 06606" in phi.values()   # one LOCATION token


def test_city_state_zip_without_label_is_redacted():
    clean, _ = deid.scrub("Patient resides in Kingland, TX 75001 with family.")
    assert "Kingland" not in clean and "75001" not in clean
    assert "with family" in clean


def test_address_recognizer_patterns_and_bare_zip_score():
    r = address.address_recognizer()
    assert r.name == address.NAME == "street_address_regex"
    assert spans(r, "Address: 609 Stacey Roads, New Brendaton, IN 06606    Attending: Dr. Young", "LOCATION")[0] == \
        ("609 Stacey Roads, New Brendaton, IN 06606", 0.85)
    assert ("12 Oak Street Apt 4", 0.6) in spans(r, "lives at 12 Oak Street Apt 4 with family", "LOCATION")
    assert spans(r, "WBC 11000", "LOCATION") == [("11000", 0.35)]        # a lab value, below threshold


# ---------------------------------------------------------------- date filter

def test_dosing_frequency_and_duration_are_not_redacted():
    clean, _ = deid.scrub("Medications: sertraline 50 mg daily; atorvastatin 40 mg nightly. Follow up in 2 weeks.")
    for keep in ("daily", "nightly", "2 weeks", "sertraline 50 mg"):
        assert keep in clean, clean


def test_calendar_dates_are_still_redacted():
    clean, _ = deid.scrub("DOB: 1985-03-12. Admitted 03/05/2024 and discharged March 9, 2024.")
    for gone in ("1985-03-12", "03/05/2024", "March 9"):
        assert gone not in clean, clean


@pytest.mark.parametrize("span, identifying", [
    ("1985-03-12", True), ("03/05/2024", True), ("03-05-24", True), ("March 9, 2024", True),
    ("Sept. 5", True), ("the 5th", True), ("2024", True),
    ("daily", False), ("nightly", False), ("2 weeks", False), ("48 hours", False),
    ("2 weeks later", False), ("tonight", False), ("", False),
])
def test_is_identifying_date(span, identifying):
    assert is_identifying_date(span) is identifying
    assert deid._is_identifying_date is is_identifying_date
    assert date_filter.DATE_LIKE.flags & date_filter.re.IGNORECASE


# ---------------------------------------------------------------- person trim

def test_bare_title_is_never_a_person_token():
    clean, phi = deid.scrub("Attending: Dr. Hawkins    Date of service: 2026-02-02")
    assert "Hawkins" not in clean
    assert "Attending: Dr. <PERSON_" in clean, clean          # the title survives, the name is the token
    assert "Dr" not in phi.values() and "Date" not in phi.values()
    assert all(v.strip() not in ("Dr", "Dr.", "Attending", "Date") for v in phi.values())


def test_person_span_is_trimmed_of_leading_title_and_trailing_label():
    assert deid._trim_person is trim_person
    assert trim_person("Patient: Joshua Duncan DOB: 1975", 9, 26) == (9, 22)   # "Joshua Duncan"
    assert trim_person("Seen by Dr Young today", 8, 16) == (11, 16)          # "Young"
    assert trim_person("Attending: Dr.", 11, 14) is None                    # nothing left
    assert trim_person("Plan", 0, 4) is None
    assert person_trim.TITLES & person_trim.LABELS == {"attending", "patient", "physician", "provider"}


def test_ocr_style_line_keeps_labels_out_of_the_map():
    clean, phi = deid.scrub("Patient: Joshua Duncan DOB: 1975-06-15 MAN: 8275367")
    assert "Joshua Duncan" in phi.values(), phi
    assert not any(v.endswith("DOB") for v in phi.values()), phi
    assert "8275367" not in clean and phi.get("<MRN_1>") == "8275367"    # OCR-damaged label, item 14
