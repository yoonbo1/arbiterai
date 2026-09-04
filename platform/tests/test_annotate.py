"""worker/annotate.py with the real models (medspaCy host pipeline, en_core_med7_lg,
en_ner_bc5cdr_md), installed into .venv by `make venv-clinical`. Skipped when they are missing.

The fixture text is the de-identified discharge summary the synthetic generator produces
(scripts/make_synthetic_docs.py), i.e. what worker/deid.py hands the annotate node; the OCR
variant mirrors what Tesseract returns for the scanned copies (no indentation, 'HbAic', 'Pian').
The LLM layer is exercised against a stubbed HTTP call only."""
import json
import os

import pytest

from worker import annotate, llm, store

pytest.importorskip("medspacy")
for _m in ("en_core_med7_lg", "en_ner_bc5cdr_md"):
    pytest.importorskip(_m)

CLEAN = """DISCHARGE SUMMARY
Patient: <PERSON_3>    DOB: <DATE_TIME_2>    MRN: <MRN_1>
Phone: <PHONE_NUMBER_1>    Address: <LOCATION_1>
Attending: <PERSON_2>. <PERSON_1>    Date of service: <DATE_TIME_1>
Diagnoses
  - COPD
  - atrial fibrillation
  - No evidence of pneumonia. Denies chest pain.
Medications
  - sertraline 50 mg daily
  - metformin 500 mg BID
  - albuterol PRN
Allergies
  penicillin (rash)
Vitals and labs
  BP 116/88   HbA1c 9.0%   LDL 144 mg/dL
Plan
  Follow up with Dr. <PERSON_1> in 2 weeks. Continue current medications. Low-sodium diet.
  Family history of coronary artery disease.
"""

OCR = """DISCHARGE SUMMARY

Patient: <PERSON_4>: <DATE_TIME_2> MRN- <MRN_1>
Phone: <PHONE_NUMBER_1> Address: <LOCATION_1>
Attending: <PERSON_3>. <PERSON_2> of service: <DATE_TIME_1>

Diagnoses
- major depressive disorder
- type 2 diabetes mellitus
- No evidence of syncope. Denies pneumonia.
Medications
- lisinopril 10 mg daily
- metformin 500 mg BID
- apixaban 5 mg BID
Allergies
NKDA
Vitals and labs
BP 146/72 HbAic 5.7% LDL 98 mg/dL
Pian
Follow up with Dr. <PERSON_1> in 2 weeks. Continue current medications. Low-sodium diet.
Family history of type 2 diabetes mellitus.
"""


@pytest.fixture(scope="module")
def clean_facts():
    return annotate.annotate_pages([CLEAN])[0]


@pytest.fixture(scope="module")
def ocr_facts():
    return annotate.annotate_pages([OCR])[0]


def by_kind(facts, kind):
    return [f for f in facts if f.kind == kind]


# ---------------------------------------------------------------- shape

def test_fact_shape_and_vocabularies(clean_facts):
    assert clean_facts
    for f in clean_facts:
        assert isinstance(f, annotate.Fact)
        assert f.page == 1 and 0 <= f.start < f.end <= len(CLEAN)
        assert CLEAN[f.start:f.end] == f.text
        assert f.kind in annotate.KINDS and f.assertion in annotate.ASSERTIONS
        assert f.extractor in ("rules", "ner", "llm") and 0 < f.confidence <= 1
        assert f.normalized == f.normalized.lower() and "  " not in f.normalized
        assert isinstance(f.attributes, dict)
        assert f.date_token == "<DATE_TIME_1>"        # the nearest date token on the page (date of service)
    assert [(f.start, f.end) for f in clean_facts] == sorted((f.start, f.end) for f in clean_facts)


def test_kinds_match_the_clinical_facts_check_constraint():
    allowed = {"problem", "medication", "lab", "vital", "procedure", "allergy", "immunization", "referral", "plan", "other"}
    assert set(annotate.KINDS) <= allowed
    assert set(annotate.ASSERTIONS) == {"present", "absent", "possible", "conditional", "historical", "family"}


# ---------------------------------------------------------------- problems + assertion

def test_problems_present_absent_family(clean_facts):
    probs = {(f.normalized, f.assertion) for f in by_kind(clean_facts, "problem")}
    assert probs == {("copd", "present"), ("atrial fibrillation", "present"),
                     ("pneumonia", "absent"), ("chest pain", "absent"),
                     ("coronary artery disease", "family")}
    fam = next(f for f in clean_facts if f.assertion == "family")
    assert fam.extractor == "rules"                   # the family-history rule fires even if NER missed it
    for f in by_kind(clean_facts, "problem"):
        assert f.section in ("diagnoses", "observation_and_plan")


def test_negation_cue_is_trimmed_from_the_span(clean_facts):
    chest = next(f for f in clean_facts if f.normalized == "chest pain")
    assert chest.text == "chest pain" and chest.assertion == "absent"
    assert "denies" not in chest.text.lower()


def test_list_items_are_taken_whole(ocr_facts):
    probs = {(f.normalized, f.assertion) for f in by_kind(ocr_facts, "problem")}
    assert ("type 2 diabetes mellitus", "present") in probs
    assert ("major depressive disorder", "present") in probs
    assert ("type 2 diabetes mellitus", "family") in probs
    assert ("syncope", "absent") in probs and ("pneumonia", "absent") in probs
    assert not {n for n, a in probs if a == "present"} & {"syncope", "pneumonia", "diabetes mellitus", "depressive disorder"}


def test_bullets_bound_negation_scope():
    text = "Diagnoses\n- No evidence of pneumonia\n- COPD\n- Denies chest pain\n- hypertension\n"
    facts = annotate.annotate_pages([text])[0]
    probs = {(f.normalized, f.assertion) for f in by_kind(facts, "problem")}
    assert probs == {("pneumonia", "absent"), ("copd", "present"), ("chest pain", "absent"), ("hypertension", "present")}


def test_family_history_variants():
    text = ("HPI\nPatient reports FHx CAD and stroke. Mother with breast cancer at age 60.\n"
            "Family History\n  Father: type 2 diabetes mellitus\n")
    facts = annotate.annotate_pages([text])[0]
    fam = {f.normalized for f in facts if f.kind == "problem" and f.assertion == "family"}
    assert {"cad", "stroke", "breast cancer", "type 2 diabetes mellitus"} <= fam
    assert not [f for f in facts if f.kind == "problem" and f.assertion == "present"]


# ---------------------------------------------------------------- medications

def test_medications_with_dose_and_frequency(clean_facts):
    meds = {f.normalized: f for f in by_kind(clean_facts, "medication")}
    assert set(meds) == {"sertraline", "metformin", "albuterol"}
    assert meds["sertraline"].attributes["dose"] == "50 mg" and meds["sertraline"].attributes["frequency"] == "daily"
    assert meds["metformin"].attributes["dose"] == "500 mg" and meds["metformin"].attributes["frequency"] == "BID"
    assert meds["albuterol"].attributes.get("dose") is None and meds["albuterol"].attributes["frequency"] == "PRN"
    for f in meds.values():
        assert f.assertion == "present" and f.section == "medications"
    assert meds["sertraline"].text == "sertraline 50 mg daily"


def test_medication_facts_in_prose_come_from_med7():
    text = "Hospital Course\nShe was started on lisinopril 10 mg daily and continued on metformin.\n"
    facts = annotate.annotate_pages([text])[0]
    meds = {f.normalized: f for f in by_kind(facts, "medication")}
    assert "lisinopril" in meds and meds["lisinopril"].extractor == "ner"
    assert meds["lisinopril"].attributes.get("dose") == "10 mg"
    assert meds["lisinopril"].attributes.get("frequency") == "daily"


# ---------------------------------------------------------------- labs, vitals, allergies

def test_labs_and_vital(clean_facts, ocr_facts):
    for facts, a1c, ldl, bp in ((clean_facts, "9.0", "144", "116/88"), (ocr_facts, "5.7", "98", "146/72")):
        labs = {f.normalized: f.attributes for f in by_kind(facts, "lab")}
        assert labs["hba1c"] == {"value": a1c, "unit": "%"}
        assert labs["ldl"] == {"value": ldl, "unit": "mg/dL"}
        vitals = {f.normalized: f.attributes for f in by_kind(facts, "vital")}
        assert vitals["bp"]["value"] == bp
        assert all(f.section == "labs_and_studies" for f in by_kind(facts, "lab") + by_kind(facts, "vital"))


@pytest.mark.parametrize("spelling", ["HbA1c", "HbAic", "HbAlc", "HbAt1c", "HgbA1c", "Hb A1c", "A1c", "Hemoglobin A1c"])
def test_a1c_spellings_seen_in_ocr(spelling):
    facts = annotate.annotate_pages([f"Vitals and labs\nBP 120/80 {spelling} 7.2% LDL 90 mg/dL\n"])[0]
    labs = {f.normalized: f.attributes for f in by_kind(facts, "lab")}
    assert labs["hba1c"] == {"value": "7.2", "unit": "%"}, facts
    assert labs["ldl"] == {"value": "90", "unit": "mg/dL"}


def test_allergy_with_reaction_and_never_a_medication(clean_facts):
    al = by_kind(clean_facts, "allergy")
    assert [(f.normalized, f.attributes) for f in al] == [("penicillin", {"reaction": "rash"})]
    assert al[0].section == "allergy" and al[0].assertion == "present"
    assert "penicillin" not in {f.normalized for f in by_kind(clean_facts, "medication")}
    assert "rash" not in {f.normalized for f in by_kind(clean_facts, "problem")}   # a reaction, not a diagnosis


def test_nkda_yields_no_allergy(ocr_facts):
    assert by_kind(ocr_facts, "allergy") == []
    facts = annotate.annotate_pages(["Allergies: NKDA\nMedications\n- aspirin 81 mg daily\n"])[0]
    assert by_kind(facts, "allergy") == []
    assert {f.normalized for f in by_kind(facts, "medication")} == {"aspirin"}


def test_allergy_section_does_not_make_the_rest_of_the_note_conditional(clean_facts):
    """medspaCy's default section attributes set is_hypothetical on the allergy section body,
    which (without a section boundary) leaked over the whole tail of the note."""
    assert all(f.assertion != "conditional" for f in clean_facts)


# ---------------------------------------------------------------- plan, placeholders, sections

def test_follow_up_plan(clean_facts):
    plans = by_kind(clean_facts, "plan")
    assert len(plans) == 1
    assert plans[0].attributes["when"] == "2 weeks"
    assert plans[0].section == "observation_and_plan" and plans[0].text.startswith("Follow up with")


def test_placeholders_never_become_facts(clean_facts, ocr_facts):
    for facts in (clean_facts, ocr_facts):
        for f in facts:
            assert not annotate.PLACEHOLDER.fullmatch(f.text.strip())
            assert not annotate.PLACEHOLDER.search(f.normalized)
            if f.kind != "plan":                       # a plan sentence may mention <PERSON_1>; entities may not
                assert not annotate.PLACEHOLDER.search(f.text)
    lonely = annotate.annotate_pages(["Diagnoses\n- <PERSON_1>\n- <DATE_TIME_1>\nMedications\n- <PERSON_2> 10 mg daily\n"])[0]
    assert [f for f in lonely if f.kind in ("problem", "medication")] == []


@pytest.mark.parametrize("header, category", [
    ("Diagnoses", "diagnoses"), ("Medications", "medications"), ("Meds:", "medications"),
    ("Current Medications", "medications"), ("Home Meds", "medications"), ("Allergies", "allergy"),
    ("Vitals and labs", "labs_and_studies"), ("Laboratory Data:", "labs_and_studies"),
    ("Plan", "observation_and_plan"), ("Assessment and Plan", "observation_and_plan"),
    ("Problem List", "problem_list"), ("Family History", "family_history"),
    ("Past Medical History", "past_medical_history"), ("Social History", "social_history"),
    ("Hospital Course", "hospital_course"), ("Physical Exam", "physical_exam"), ("HPI", "history_of_present_illness"),
    ("Chief Complaint", "chief_complaint"), ("Review of Systems:", "review_of_systems"), ("PLAN:", "observation_and_plan"),
])
def test_header_variants_are_sectioned(header, category):
    text = f"Note\n{header}\n  some content here\nOther:\n  more\n"
    secs = annotate.page_sections(text)
    cats = [c for c, *_ in secs]
    assert category in cats, secs
    i = cats.index(category)
    _, title_start, body_start, body_end = secs[i]
    assert text[title_start:body_start].strip().lower().startswith(header.lower().rstrip(":"))
    assert "some content here" in text[body_start:body_end]


def test_header_at_page_start_is_sectioned():
    secs = annotate.page_sections("Medications\n- metformin 500 mg BID\n")
    assert secs[0][0] == "medications"


def test_past_medical_history_is_historical():
    facts = annotate.annotate_pages(["Past Medical History\n- hypertension\n- COPD\nPlan\n- continue care\n"])[0]
    assert {(f.normalized, f.assertion) for f in by_kind(facts, "problem")} == {("hypertension", "historical"), ("copd", "historical")}


# ---------------------------------------------------------------- logging hygiene

def test_pyrush_logs_nothing_to_stderr(capfd):
    capfd.readouterr()
    facts = annotate.annotate_pages([CLEAN, OCR])
    out, err = capfd.readouterr()
    assert err == ""                                  # PyRuSH would otherwise log every token of the text
    for line in CLEAN.splitlines():
        if line.strip():
            assert line.strip() not in out            # our own log line carries counts only
    assert "[annotate]" in out and "facts" in out
    assert len(facts) == 2


def test_empty_and_blank_pages():
    assert annotate.annotate_pages(["", "   \n"]) == [[], []]
    assert annotate.annotate_pages([]) == []


# ---------------------------------------------------------------- graph gate

def _graph():
    pytest.importorskip("langgraph")                  # worker/graph.py needs it; the host venv may not have it
    from worker import graph
    return graph


def test_graph_annotate_gate(monkeypatch):
    graph = _graph()
    monkeypatch.setenv("ANNOTATE", "0")
    monkeypatch.setattr(annotate, "annotate_pages", lambda *a, **k: (_ for _ in ()).throw(AssertionError("models must not run")))
    out = graph.annotate_pages({"deidentified": True, "raw_text": ["a", "b", "c"], "job_id": "j"})
    assert out == {"facts": [[], [], []]}
    with pytest.raises(AssertionError):
        graph.annotate_pages({"deidentified": False, "raw_text": ["a"], "job_id": "j"})


def test_graph_annotate_runs_when_enabled(monkeypatch):
    graph = _graph()
    monkeypatch.setenv("ANNOTATE", "1")
    calls = []
    monkeypatch.setattr(annotate, "annotate_pages", lambda texts, usage=None: (calls.append(texts), [[]] * len(texts))[1])
    out = graph.annotate_pages({"deidentified": True, "raw_text": ["x"], "job_id": "j", "usage": {"small": 3}})
    assert calls == [["x"]] and out["facts"] == [[]] and out["usage"] == {"small": 3}
    assert "annotate" in [n for n in graph.build_ingest().nodes]


def test_counts_by_kind(clean_facts):
    c = annotate.counts_by_kind([clean_facts])
    assert c["problem"] == 5 and c["medication"] == 3 and c["lab"] == 2 and c["vital"] == 1 and c["allergy"] == 1
    assert annotate.counts_by_kind([[f.as_dict() for f in clean_facts]]) == c


# ---------------------------------------------------------------- chunk offsets (store)

def test_split_with_offsets_aligns_with_page_text():
    # 60 short lines, several of them identical: the offset search must still advance monotonically
    text = "\n".join(f"line {i % 7}: vitals stable, tolerating diet, ambulating in hallway." for i in range(60))
    pieces = store.split_with_offsets(text)
    assert len(pieces) > 3
    starts = []
    for piece, s, e in pieces:
        assert s is not None and text[s:e] == piece
        starts.append(s)
    assert starts == sorted(starts) and len(set(starts)) == len(starts)
    assert starts[0] == 0 and pieces[-1][2] == len(text)
    # chunk overlap (120 chars ~ two lines): the next piece starts before the previous one ends
    assert all(pieces[i + 1][1] < pieces[i][2] for i in range(len(pieces) - 1))
    assert store.split_with_offsets("") == []


def test_chunk_for_picks_largest_overlap():
    chunks = [(1, 0, 100), (2, 80, 200), (3, 180, 300), (4, None, None)]
    assert store.chunk_for(chunks, 10, 20) == 1
    assert store.chunk_for(chunks, 90, 150) == 2         # 10 chars in 1, 60 in 2
    assert store.chunk_for(chunks, 190, 195) in (2, 3)
    assert store.chunk_for(chunks, 400, 410) is None
    assert store.chunk_for([], 0, 5) is None


def test_index_document_writes_offsets_and_facts(monkeypatch):
    """The SQL path with the pool replaced by a recording fake."""
    from types import SimpleNamespace
    text = "Diagnoses\n- COPD\nMedications\n- metformin 500 mg BID\n"
    facts = annotate.annotate_pages([text])
    calls = []

    class Cur:
        def __init__(self):
            self._ret = []

        def execute(self, sql, params=None):
            calls.append((sql, params))

        def executemany(self, sql, rows, returning=False):
            rows = list(rows)
            calls.append((sql, rows))
            if returning:
                self._ret = [(100 + i,) for i in range(len(rows))]

        def fetchone(self):
            return self._ret.pop(0)

        def nextset(self):
            return bool(self._ret)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Con:
        def cursor(self):
            return Cur()

    from contextlib import contextmanager

    @contextmanager
    def tenant_conn(tid):
        yield Con()

    monkeypatch.setattr(store, "tenant_conn", tenant_conn)
    monkeypatch.setattr(store, "embed", lambda texts: [[0.0] * store.EMBED_DIM for _ in texts])
    page = SimpleNamespace(number=1, route="text")
    n = store.index_document(tenant_id="t", patient_id="p", document_id="d", pages=[page], texts=[text],
                             phi_map={}, facts=facts)
    assert n == 1
    sqls = [c[0] for c in calls]
    assert any("DELETE FROM clinical_facts" in s for s in sqls)
    chunk_insert = next(c for c in calls if c[0].startswith("INSERT INTO chunks"))
    assert "char_start, char_end" in chunk_insert[0] and "RETURNING id" in chunk_insert[0]
    assert chunk_insert[1][0][-2:] == (0, len(text.strip()))
    fact_insert = next(c for c in calls if c[0].startswith("INSERT INTO clinical_facts"))
    assert len(fact_insert[1]) == len(facts[0]) == 2
    for row in fact_insert[1]:
        assert row[3] == 100                              # chunk_id of the only chunk on the page
        assert row[6] in ("problem", "medication")
    assert "UPDATE documents SET status='indexed'" in sqls[-1]


# ---------------------------------------------------------------- LLM layer (stubbed HTTP)

class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def _stub_llm(monkeypatch, facts_json, requests):
    def post(url, timeout, json):
        requests.append((url, json))
        return _Resp({"choices": [{"message": {"content": facts_json}}], "usage": {"total_tokens": 42}})
    monkeypatch.setattr(llm.httpx, "post", post)


TEXT_FOR_LLM = ("Patient: <PERSON_1>\nMedications\n  - sertraline 50 mg\n  - metformin 500 mg BID\n"
                "Hospital Course\n  Seen by <PERSON_2> on the ward.\nPlan\n  Sugar test came back at 140 this morning.\n")


def test_llm_layer_fills_attributes_and_adds_verbatim_facts(monkeypatch):
    monkeypatch.setattr(annotate.deid, "contains_phi", lambda text: False)
    reqs = []
    _stub_llm(monkeypatch, json.dumps({"facts": [
        {"kind": "medication", "text": "sertraline 50 mg", "name": "sertraline", "frequency": "daily", "dose": "999 mg"},
        {"kind": "lab", "text": "Sugar test came back at 140", "name": "glucose", "value": "140"},   # prose only the LLM reads
        {"kind": "medication", "text": "furosemide", "name": "furosemide", "frequency": "BID"},     # invented: not verbatim
        {"kind": "problem", "text": "<PERSON_2>", "name": "person"},                                # not in a sent body
    ]}), reqs)
    usage = {}
    facts = annotate.annotate_pages([TEXT_FOR_LLM], llm_enabled=True, usage=usage)[0]
    meds = {f.normalized: f for f in facts if f.kind == "medication"}
    assert meds["sertraline"].extractor == "rules"
    assert meds["sertraline"].attributes == {"dose": "50 mg", "frequency": "daily"}     # filled, never overwritten
    assert set(meds) == {"sertraline", "metformin"}                                     # 'furosemide' was not verbatim
    lab, = [f for f in facts if f.kind == "lab"]
    assert lab.extractor == "llm" and lab.confidence == 0.6 and lab.normalized == "glucose"
    assert lab.text == "Sugar test came back at 140" and lab.attributes == {"value": "140"}
    assert lab.assertion == "present" and lab.section == "observation_and_plan"         # ConText, not the model
    assert not [f for f in facts if "<PERSON_" in f.text]
    assert usage == {"small": 42}
    # request shape: json_schema response format, and only section bodies were sent
    (url, body), = reqs
    assert url.endswith("/chat/completions")
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "clinical_facts"
    sent = body["messages"][1]["content"]
    assert "sertraline 50 mg" in sent and "Sugar test came back at 140 this morning." in sent
    assert "<PERSON_" not in sent and "on the ward" not in sent                         # header line / hospital course not sent
    assert body["temperature"] == 0


def test_llm_output_failing_phi_check_is_dropped(monkeypatch):
    monkeypatch.setattr(annotate.deid, "contains_phi", lambda text: True)
    reqs = []
    _stub_llm(monkeypatch, json.dumps({"facts": [{"kind": "lab", "text": "Sugar test came back at 140", "name": "glucose"}]}), reqs)
    facts = annotate.annotate_pages([TEXT_FOR_LLM], llm_enabled=True)[0]
    assert not [f for f in facts if f.extractor == "llm"]
    assert len(reqs) == 1


def test_llm_layer_is_off_by_default_and_survives_errors(monkeypatch):
    calls = []
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: calls.append(1))
    monkeypatch.delenv("ANNOTATE_LLM", raising=False)
    annotate.annotate_pages([TEXT_FOR_LLM])
    assert calls == []
    monkeypatch.setenv("ANNOTATE_LLM", "1")
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("endpoint down")))
    facts = annotate.annotate_pages([TEXT_FOR_LLM])[0]         # the optional layer never fails the page
    assert {f.normalized for f in facts if f.kind == "medication"} >= {"sertraline", "metformin"}


def test_llm_extract_json_parses_fenced_output(monkeypatch):
    monkeypatch.setattr(llm.httpx, "post", lambda url, timeout, json: _Resp(
        {"choices": [{"message": {"content": "```json\n{\"facts\": []}\n```"}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}}))
    assert llm.extract_json("small", "s", "u", annotate.LLM_SCHEMA) == ({"facts": []}, 7)
    monkeypatch.setattr(llm.httpx, "post", lambda url, timeout, json: _Resp({"choices": [{"message": {"content": "not json"}}]}))
    assert llm.extract_json("small", "s", "u", annotate.LLM_SCHEMA) == (None, 0)
