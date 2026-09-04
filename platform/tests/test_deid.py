"""worker/deid.py against the real Presidio engine with en_core_web_sm (tests/conftest.py pins
SPACY_MODEL before import). The analyzer is built once per session on first use.

Assertions are structural: raw identifiers must be gone, tokens must be well formed and
reversible. spaCy entity labels are only asserted where they are stable for this model;
cases that en_core_web_sm cannot satisfy are kept as xfail so the gap stays visible."""
import re

import pytest
from presidio_analyzer import RecognizerResult

from worker import deid

TOKEN = re.compile(r"<[A-Z_]+_\d+>")

NAME = "John Smith"
DOB = "1961-04-12"
MRN = "1234567"
PHONE = "+1-921-899-3518x19093"
EMAIL = "john.smith@example.com"
# Presidio's US_SSN validator rejects the classic 123-45-6789 (sequential digits), so the
# fixture uses a structurally valid number; the classic one has its own xfail below.
SSN = "536-22-8191"
RAW = [NAME, DOB, MRN, PHONE, EMAIL, SSN]

SUMMARY = (
    "DISCHARGE SUMMARY\n"
    f"Patient: {NAME}. DOB: {DOB}. MRN: {MRN}.\n"
    f"Mr. {NAME} was admitted with community-acquired pneumonia and started on ceftriaxone "
    "1 g IV daily. Blood cultures were negative at 48 hours.\n"
    f"Contact phone: {PHONE}. Email: {EMAIL}. SSN: {SSN}.\n"
    "Discharged home in stable condition; follow up with primary care in 2 weeks."
)


@pytest.fixture(scope="module")
def scrubbed():
    return deid.scrub(SUMMARY)


def assert_well_formed(clean: str, phi_map: dict[str, str]) -> None:
    """Every '<' in the text belongs to exactly one complete token that is in the map; no
    token is opened inside another."""
    assert not re.search(r"<[^<>]*<", clean), clean
    residue = TOKEN.sub("", clean)
    assert "<" not in residue and ">" not in residue, clean
    assert set(TOKEN.findall(clean)) == set(phi_map)
    assert all(deid._TOKEN.fullmatch(t) for t in phi_map)


# ---------------------------------------------------------------- engine

def test_analyzer_uses_small_model_and_is_a_singleton():
    assert deid.SPACY_MODEL == "en_core_web_sm"
    assert deid.analyzer() is deid.analyzer()
    names = {r.name for r in deid.analyzer().registry.recognizers}
    assert "phone_regex" in names and "PatternRecognizer" in names       # our MRN recognizer


# ---------------------------------------------------------------- scrub()

def test_no_raw_phi_survives(scrubbed):
    clean, phi_map = scrubbed
    for raw in RAW:
        assert raw not in clean, raw
    assert set(RAW) <= set(phi_map.values())
    # clinical content is untouched
    for kept in ("DISCHARGE SUMMARY", "community-acquired pneumonia", "ceftriaxone 1 g IV daily",
                 "Blood cultures were negative", "stable condition"):
        assert kept in clean


def test_tokens_are_well_formed(scrubbed):
    clean, phi_map = scrubbed
    assert_well_formed(clean, phi_map)
    assert phi_map                                    # something was actually redacted
    for token in phi_map:
        etype, n = deid._TOKEN.fullmatch(token).groups()
        assert etype in deid.ENTITIES
        assert int(n) >= 1
    # numbering is per entity type and dense (1..n)
    by_type: dict[str, set[int]] = {}
    for token in phi_map:
        etype, n = deid._TOKEN.fullmatch(token).groups()
        by_type.setdefault(etype, set()).add(int(n))
    assert all(ns == set(range(1, len(ns) + 1)) for ns in by_type.values())


def test_labels_survive_and_types_are_stable(scrubbed):
    """Pattern-based recognizers (ours and Presidio's) produce stable types; only the digits /
    address are replaced so the field label stays readable for the model."""
    clean, phi_map = scrubbed
    assert re.search(r"MRN: <MRN_\d+>\.", clean)
    assert re.search(r"DOB: <DATE_TIME_\d+>\.", clean)
    assert re.search(r"SSN: <US_SSN_\d+>\.", clean)
    assert re.search(r"Email: <EMAIL_ADDRESS_\d+>\.", clean)
    assert re.search(r"phone: <PHONE_NUMBER_\d+>\.", clean)
    assert re.search(r"Patient: <PERSON_\d+>\.", clean)
    for value, etype in ((MRN, "MRN"), (EMAIL, "EMAIL_ADDRESS"), (PHONE, "PHONE_NUMBER"), (SSN, "US_SSN")):
        token = next(t for t, v in phi_map.items() if v == value)
        assert token.startswith(f"<{etype}_")


def test_repeated_name_maps_to_one_token(scrubbed):
    clean, phi_map = scrubbed
    assert SUMMARY.count(NAME) == 2
    name_tokens = [t for t, v in phi_map.items() if v == NAME]
    assert len(name_tokens) == 1
    assert clean.count(name_tokens[0]) == 2
    assert len(set(phi_map.values())) == len(phi_map)         # value <-> token is a bijection


def test_restore_round_trips(scrubbed):
    clean, phi_map = scrubbed
    assert clean != SUMMARY
    assert deid.restore(clean, phi_map) == SUMMARY


def test_restore_leaves_unknown_tokens_and_citations_alone():
    assert deid.restore("<PERSON_9> and <MRN_1> [12]", {"<MRN_1>": "42"}) == "<PERSON_9> and 42 [12]"
    assert deid.restore("no tokens [12]", {}) == "no tokens [12]"
    assert deid.restore("", {"<MRN_1>": "42"}) == ""


def test_scrub_empty_and_blank_text():
    assert deid.scrub("") == ("", {})
    assert deid.scrub("  \n\t") == ("  \n\t", {})


@pytest.mark.parametrize("text", ["MRN: 1234567", "MRN:1234567", "MRN 1234567",
                                  "MRN# 1234567", "MRN#1234567", "MRN: 1234567890"])
def test_labeled_mrn_forms(text):
    clean, phi_map = deid.scrub(text)
    digits = text.split("MRN")[1].lstrip(":# ")
    assert digits not in clean
    assert clean.startswith("MRN")                     # the label is kept, only digits replaced
    assert phi_map == {"<MRN_1>": digits}


@pytest.mark.parametrize("phone", ["+1-921-899-3518x19093", "(555) 201-8842 ext. 12",
                                   "555.201.8842", "921-899-3518 extension 7", "+1 921 899 3518"])
def test_phone_forms_with_extensions(phone):
    text = f"Contact phone: {phone}. Thanks."
    clean, phi_map = deid.scrub(text)
    assert phone not in clean
    assert_well_formed(clean, phi_map)
    assert phi_map.get("<PHONE_NUMBER_1>") == phone
    assert deid.restore(clean, phi_map) == text


def test_uncommon_hyphenated_name_after_honorific():
    clean, phi_map = deid.scrub("Dr. Priya Raghunathan-Okafor reviewed the chart.")
    assert "Raghunathan" not in clean
    assert "Priya Raghunathan-Okafor" in phi_map.values()


# ---------------------------------------------------------------- scrub_pages()

def test_scrub_pages_keeps_count_and_shares_tokens_across_pages():
    pages = [f"Page one. Patient {NAME}, MRN: {MRN}, seen for follow-up.",
             "",                                            # blank page (scanned separator)
             f"Page two. {NAME} tolerated the procedure. Fax 921-899-3518.",
             f"Page three. MRN: {MRN} confirmed; call 921-899-3518 with questions."]
    out, phi_map = deid.scrub_pages(pages)

    assert len(out) == len(pages)
    assert out[1] == ""
    for page in out:
        assert NAME not in page and MRN not in page and "921-899-3518" not in page
        assert_well_formed(page, {t: v for t, v in phi_map.items() if t in page})

    name_tok = next(t for t, v in phi_map.items() if v == NAME)
    mrn_tok = next(t for t, v in phi_map.items() if v == MRN)
    fax_tok = next(t for t, v in phi_map.items() if v == "921-899-3518")
    assert name_tok in out[0] and name_tok in out[2]          # same person -> same token
    assert mrn_tok in out[0] and mrn_tok in out[3]
    assert fax_tok in out[2] and fax_tok in out[3]
    assert len(phi_map) == 3
    assert [deid.restore(p, phi_map) for p in out] == pages


def test_scrub_pages_empty_list():
    assert deid.scrub_pages([]) == ([], {})


# ---------------------------------------------------------------- overlap resolution

def rr(etype, start, end, score):
    return RecognizerResult(entity_type=etype, start=start, end=end, score=score)


def test_select_merges_overlaps_into_their_union_typed_by_the_best_member():
    results = [
        rr("PHONE_NUMBER", 10, 22, 0.6),    # 555-201-8842
        rr("MRN", 14, 22, 0.3),             # digit run inside the phone number: type from the phone
        rr("DATE_TIME", 30, 34, 0.85),      # a year ...
        rr("DATE_TIME", 30, 40, 0.85),      # ... inside a full date: union is the full date
        rr("LOCATION", 50, 58, 0.85),       # NER city ...
        rr("LOCATION", 50, 65, 0.6),        # ... inside "City, ST 12345": union keeps the ZIP covered
        rr("PERSON", 60, 62, 0.4),          # chained overlap joins the same group
        rr("US_SSN", 70, 70, 0.9),          # empty span is dropped even though it scores highest
    ]
    chosen = deid._select(results)
    assert [(c.entity_type, c.start, c.end) for c in chosen] == [
        ("LOCATION", 50, 65), ("DATE_TIME", 30, 40), ("PHONE_NUMBER", 10, 22)]
    # reverse text order so in-place replacement never shifts a later span
    assert [c.start for c in chosen] == sorted((c.start for c in chosen), reverse=True)
    assert deid._select([]) == []


@pytest.mark.parametrize("text, gone", [
    ("Tel: 9218993518 for records.", ["9218993518"]),                     # phone- and MRN-shaped run
    ("MRN 9218993518 and phone 921-899-3518 ext 7.", ["9218993518", "921-899-3518 ext 7"]),
    ("Call 555-201-8842 ext. 12 or MRN: 5552018842 for records.", ["555-201-8842", "5552018842"]),
    ("DOB 1961-04-12; seen 2024-01-05 and again in 2024.", ["1961-04-12", "2024-01-05"]),
])
def test_overlapping_spans_yield_well_formed_output(text, gone):
    clean, phi_map = deid.scrub(text)
    for raw in gone:
        assert raw not in clean, (raw, clean)
    assert_well_formed(clean, phi_map)
    assert deid.restore(clean, phi_map) == text


# ---------------------------------------------------------------- contains_phi()

def test_contains_phi_false_for_tokens_and_citations(scrubbed):
    clean, _ = scrubbed
    assert deid.contains_phi(clean) is False
    assert deid.contains_phi("<PERSON_1> was started on ceftriaxone [12] and discharged on "
                             "<DATE_TIME_2> [3]. MRN <MRN_1> [1234].") is False
    assert deid.contains_phi("The excerpts do not contain the answer.") is False
    assert deid.contains_phi("") is False


def test_contains_phi_true_for_raw_identifiers():
    assert deid.contains_phi(f"The patient's SSN is {SSN}.") is True
    assert deid.contains_phi(f"Reach the patient at {EMAIL}.") is True
    assert deid.contains_phi(f"Phone {PHONE}.") is True
    assert deid.contains_phi(f"The patient's MRN is {MRN}.") is True


def test_contains_phi_ignores_dates_and_locations():
    """Dates/locations are allowed in answers (they are clinical content, not identifiers here)."""
    assert deid.contains_phi("Admitted on 2024-01-05 and discharged 2 weeks later.") is False


# ---------------------------------------------------------------- known gaps (kept visible)

def test_contains_phi_true_for_bare_ssn():
    assert deid.contains_phi(f"Number {SSN} on file.") is True


@pytest.mark.xfail(reason="Presidio's US_SSN recognizer deliberately invalidates well-known fake "
                          "SSNs such as 123-45-6789 (sequential digits); synthetic data must use "
                          "structurally valid numbers or they survive de-identification")
def test_classic_sample_ssn_is_redacted():
    clean, _ = deid.scrub("SSN: 123-45-6789.")
    assert "123-45-6789" not in clean


@pytest.mark.xfail(reason="en_core_web_sm NER tags 'PATIENT' as the person in "
                          "'PATIENT NAME: SMITH, JOHN' and leaves the all-caps LAST, FIRST name")
def test_all_caps_last_first_name_is_redacted():
    clean, _ = deid.scrub("PATIENT NAME: SMITH, JOHN   DOB: 04/12/1961")
    assert "SMITH" not in clean and "JOHN" not in clean


def test_uncommon_name_after_terse_label_is_redacted():
    clean, _ = deid.scrub("Attending: Priya Raghunathan-Okafor.")
    assert "Raghunathan" not in clean


# ---------------------------------------------------------------- address, frequency vs date

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


def test_dosing_frequency_and_duration_are_not_redacted():
    clean, _ = deid.scrub("Medications: sertraline 50 mg daily; atorvastatin 40 mg nightly. Follow up in 2 weeks.")
    for keep in ("daily", "nightly", "2 weeks", "sertraline 50 mg"):
        assert keep in clean, clean


def test_calendar_dates_are_still_redacted():
    clean, _ = deid.scrub("DOB: 1985-03-12. Admitted 03/05/2024 and discharged March 9, 2024.")
    for gone in ("1985-03-12", "03/05/2024", "March 9"):
        assert gone not in clean, clean


# ---------------------------------------------------------------- titles and labels are not names

def test_bare_title_is_never_a_person_token():
    clean, phi = deid.scrub("Attending: Dr. Hawkins    Date of service: 2026-02-02")
    assert "Hawkins" not in clean
    assert "Attending: Dr. <PERSON_" in clean, clean          # the title survives, the name is the token
    assert "Dr" not in phi.values() and "Date" not in phi.values()
    assert all(v.strip() not in ("Dr", "Dr.", "Attending", "Date") for v in phi.values())


def test_person_span_is_trimmed_of_leading_title_and_trailing_label():
    assert deid._trim_person("Patient: Joshua Duncan DOB: 1975", 9, 26) == (9, 22)   # "Joshua Duncan"
    assert deid._trim_person("Seen by Dr Young today", 8, 16) == (11, 16)          # "Young"
    assert deid._trim_person("Attending: Dr.", 11, 14) is None                    # nothing left
    assert deid._trim_person("Plan", 0, 4) is None


def test_ocr_style_line_keeps_labels_out_of_the_map():
    clean, phi = deid.scrub("Patient: Joshua Duncan DOB: 1975-06-15 MAN: 8275367")
    assert "Joshua Duncan" in phi.values(), phi
    assert not any(v.endswith("DOB") for v in phi.values()), phi
