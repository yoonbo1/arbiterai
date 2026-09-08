"""The eval grader decides every accuracy number the project publishes, so it gets tests.

Three of the four question kinds cannot be graded by substring match. For a denial the gold
string is the condition itself, so `gold in answer` scores "the patient has pneumonia" as
correct; for an `absent` question the gold string is empty, so `"" in answer` scores every
answer correct including a fabricated value. Those two bugs would have inflated accuracy
rather than deflating it, which is the same shape as the de-identification recall metric that
read 0.967 while ZIP codes survived.
"""
import importlib.util
import os
from pathlib import Path

import pytest

EVAL = Path(__file__).resolve().parents[1] / "eval" / "run_eval.py"


@pytest.fixture(scope="module")
def grade():
    """Import the grader. run_eval.py reads credentials at module scope, so they are stubbed;
    nothing here opens a socket or a database connection."""
    os.environ.setdefault("API_KEY", "hipaa_live_test")
    os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
    os.environ.setdefault("TENANT_ID", "00000000-0000-0000-0000-000000000000")
    spec = importlib.util.spec_from_file_location("run_eval_under_test", EVAL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.grade


# ---------------------------------------------------------------- extract
@pytest.mark.parametrize("answer,expected", [
    ("The most recent HbA1c is 9.0% [7].", True),
    ("HbA1c 9.0%", True),
    ("No HbA1c was recorded for this patient.", False),
    ("The most recent HbA1c is 7.4%.", False),
])
def test_extract_matches_the_value(grade, answer, expected):
    assert grade("extract", "9.0%", answer, False)[0] is expected


def test_extract_lenient_accepts_every_item_by_its_first_two_tokens(grade):
    gold = "metformin 500 mg BID; lisinopril 10 mg daily"
    strict, lenient = grade("extract", gold, "Discharge meds: metformin 500 mg BID, lisinopril 10 mg daily.", False)
    assert strict and lenient
    # Missing the second drug fails lenient even though the first gold item is present verbatim.
    strict, lenient = grade("extract", gold, "Discharge meds: metformin 500 mg BID.", False)
    assert strict and not lenient


# ---------------------------------------------------------------- deny
@pytest.mark.parametrize("answer,expected", [
    ("There is no evidence of pneumonia in this record.", True),
    ("The patient denies pneumonia.", True),
    ("Negative for pneumonia.", True),
    ("The patient has pneumonia and was treated with antibiotics.", False),
    ("The patient was diagnosed with pneumonia.", False),
    ("Pneumonia.", False),                       # asserts it with no negation at all
])
def test_deny_requires_saying_the_finding_is_absent(grade, answer, expected):
    assert grade("deny", "pneumonia", answer, False)[0] is expected


def test_deny_would_be_graded_backwards_by_a_substring_check(grade):
    """The regression this file exists for: the gold string is the condition itself."""
    wrong = "The patient has pneumonia."
    assert "pneumonia" in wrong.lower()          # a substring grader would score this correct
    assert grade("deny", "pneumonia", wrong, False)[0] is False


# ---------------------------------------------------------------- family
@pytest.mark.parametrize("answer,expected", [
    ("Stroke is documented in the family history, not for the patient.", True),
    ("There is a family history of stroke.", True),
    ("The patient has stroke.", False),
    ("The patient was diagnosed with stroke.", False),
])
def test_family_must_not_attribute_the_condition_to_the_patient(grade, answer, expected):
    assert grade("family", "stroke", answer, False)[0] is expected


# ---------------------------------------------------------------- absent
def test_absent_counts_a_refusal_as_correct(grade):
    assert grade("absent", "", "", True)[0] is True


@pytest.mark.parametrize("answer,expected", [
    ("The ejection fraction is not documented in this note.", True),
    ("No mention of an ejection fraction.", True),
    ("That information is not available in the record.", True),
    ("The ejection fraction is 55%.", False),    # a fabrication, well formed
    ("55%", False),
])
def test_absent_rejects_a_fabricated_value(grade, answer, expected):
    assert grade("absent", "", answer, False)[0] is expected


def test_absent_would_be_graded_as_always_correct_by_a_substring_check(grade):
    """The second regression: the gold string is empty, and "" is a substring of everything."""
    fabricated = "The ejection fraction is 55%."
    assert "" in fabricated                      # a substring grader would score this correct
    assert grade("absent", "", fabricated, False)[0] is False


# ---------------------------------------------------------------- declining
@pytest.mark.parametrize("kind", ["extract", "deny", "family"])
def test_declining_is_wrong_for_every_kind_except_absent(grade, kind):
    assert grade(kind, "pneumonia", "", True)[0] is False
