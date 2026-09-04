"""Query-scope token namespace and re-identification (worker/reid.py)."""
import pytest

from worker import reid

DOC_A, DOC_B = "aaaaaaaa-0000-0000-0000-000000000001", "bbbbbbbb-0000-0000-0000-000000000002"


def chunk(cid, doc, text):
    return {"id": cid, "document_id": doc, "page": 1, "section": None, "text": text, "sim": 0.9, "score": 0.02}


def test_unify_renumbers_document_tokens_after_the_question_tokens():
    q_map = {"<PERSON_1>": "Patel"}                       # question: "What did Dr. <PERSON_1> prescribe?"
    chunks = [chunk(10, DOC_A, "Attending: Dr. <PERSON_1>. <PERSON_2> started metformin."),
              chunk(11, DOC_B, "Patient: <PERSON_1>. Seen by <PERSON_2> on <DATE_TIME_1>.")]
    out, index = reid.unify(q_map, chunks)
    assert out[0]["text"] == "Attending: Dr. <PERSON_2>. <PERSON_3> started metformin."
    assert out[1]["text"] == "Patient: <PERSON_4>. Seen by <PERSON_5> on <DATE_TIME_1>."
    assert index["<PERSON_1>"] == ("question", "<PERSON_1>")
    assert index["<PERSON_2>"] == (DOC_A, "<PERSON_1>")
    assert index["<PERSON_4>"] == (DOC_B, "<PERSON_1>")
    assert index["<DATE_TIME_1>"] == (DOC_B, "<DATE_TIME_1>")
    assert chunks[0]["text"].startswith("Attending: Dr. <PERSON_1>")   # input not mutated


def test_unify_keeps_one_label_per_person_within_a_document():
    out, index = reid.unify({}, [chunk(1, DOC_A, "<PERSON_1> ... <PERSON_1>"), chunk(2, DOC_A, "again <PERSON_1>")])
    assert out[0]["text"] == "<PERSON_1> ... <PERSON_1>" and out[1]["text"] == "again <PERSON_1>"
    assert len(index) == 1


def test_restore_uses_the_right_document_and_only_needed_tokens():
    q_map = {"<PERSON_1>": "Patel"}
    chunks = [chunk(10, DOC_A, "<PERSON_1> was started on metformin by Dr. <PERSON_2>."),
              chunk(11, DOC_B, "<PERSON_1> denies chest pain.")]
    out, index = reid.unify(q_map, chunks)
    # unified: q <PERSON_1>=Patel; A <PERSON_1>-><PERSON_2>, A <PERSON_2>-><PERSON_3>; B <PERSON_1>-><PERSON_4>
    answer = "<PERSON_2> was started on metformin by Dr. <PERSON_3> [10]"
    calls = []

    def fake_decrypt(tenant_id, doc, tokens):
        calls.append((doc, sorted(tokens)))
        vault = {DOC_A: {"<PERSON_1>": "Maria Santos", "<PERSON_2>": "Young"},
                 DOC_B: {"<PERSON_1>": "Someone Else"}}
        return {t: vault[doc][t] for t in tokens if t in vault[doc]}

    text, n = reid.restore(answer, q_map, index, "tenant", decrypt=fake_decrypt)
    assert text == "Maria Santos was started on metformin by Dr. Young [10]"
    assert n == 2
    assert calls == [(DOC_A, ["<PERSON_1>", "<PERSON_2>"])]     # DOC_B never decrypted


def test_the_patel_young_collision_is_fixed():
    """Before: the question's map was applied to a document token with the same label."""
    q_map = {"<PERSON_1>": "Patel"}
    out, index = reid.unify(q_map, [chunk(44, DOC_A, "Attending: Dr. <PERSON_1>. Started metformin 500 mg BID.")])
    assert out[0]["text"] == "Attending: Dr. <PERSON_2>. Started metformin 500 mg BID."
    answer = "Dr. <PERSON_2> started metformin 500 mg BID [44]"
    text, _ = reid.restore(answer, q_map, index, "t", decrypt=lambda t, d, toks: {"<PERSON_1>": "Young"})
    assert text == "Dr. Young started metformin 500 mg BID [44]"


def test_restore_leaves_unknown_tokens_and_needs_no_db_when_none():
    text, n = reid.restore("<PERSON_9> [1]", {}, {}, "t", decrypt=lambda *a: pytest.fail("must not decrypt"))
    assert text == "<PERSON_9> [1]" and n == 0
    text, n = reid.restore("<PERSON_1> asked", {"<PERSON_1>": "Patel"}, {"<PERSON_1>": ("question", "<PERSON_1>")}, "t",
                           decrypt=lambda *a: pytest.fail("question tokens come from memory"))
    assert text == "Patel asked" and n == 1
