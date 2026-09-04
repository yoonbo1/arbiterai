"""Query-scope token namespace and re-identification.

Every document is de-identified on its own, so each numbers its placeholders from
<PERSON_1>; a question is scrubbed the same way. Put several in one prompt and the same
label means different people, and restoring with the question's map alone swaps the wrong
name in (a question about Dr. Patel produced "Patel was started on metformin" for a chart
whose <PERSON_1> was Dr. Young). This module:

  * unify():  renumbers the tokens of the retrieved chunks and the question into ONE
              namespace for the duration of the query, keeping an index of where each
              unified token came from (the question, or a document id + original token);
  * restore(): after validation, restores only the tokens that appear in the answer:
              question tokens from the in-memory map, document tokens by decrypting that
              document's rows in phi_tokens under the tenant key.

Nothing is decrypted before the model has answered, and nothing is decrypted that the
answer does not use (minimum necessary)."""
import re

from . import store

_TOKEN = re.compile(r"<([A-Z_]+)_(\d+)>")
QUESTION = "question"


def unify(question_map: dict[str, str], chunks: list[dict]) -> tuple[list[dict], dict[str, tuple[str, str]]]:
    """Return (chunks with rewritten text, index unified_token -> (source, original_token)).
    Question tokens keep their names; document tokens are renumbered after them, one
    unified token per (document_id, original_token) so the same person in one document keeps
    one label across its chunks."""
    index: dict[str, tuple[str, str]] = {}
    counters: dict[str, int] = {}
    for tok in question_map:
        m = _TOKEN.fullmatch(tok)
        if not m:
            continue
        index[tok] = (QUESTION, tok)
        counters[m.group(1)] = max(counters.get(m.group(1), 0), int(m.group(2)))

    seen: dict[tuple, str] = {}
    out = []
    for c in chunks:
        doc = c.get("document_id")

        def sub(m, doc=doc):
            orig, etype = m.group(0), m.group(1)
            key = (doc, orig)
            if key not in seen:
                counters[etype] = counters.get(etype, 0) + 1
                uni = f"<{etype}_{counters[etype]}>"
                seen[key] = uni
                index[uni] = (doc, orig)
            return seen[key]

        nc = dict(c)
        nc["text"] = _TOKEN.sub(sub, c.get("text") or "")
        out.append(nc)
    return out, index


def restore(answer: str, question_map: dict[str, str], index: dict[str, tuple[str, str]],
            tenant_id: str, decrypt=None) -> tuple[str, int]:
    """Swap unified tokens in `answer` back to real values. Returns (text, tokens_restored).
    `decrypt(tenant_id, document_id, tokens) -> {token: value}` defaults to the database."""
    decrypt = decrypt or store.decrypt_tokens
    needed = {m.group(0) for m in _TOKEN.finditer(answer)}
    values: dict[str, str] = {}
    by_doc: dict[str, dict[str, str]] = {}          # document_id -> {original: unified}
    for uni in needed:
        src = index.get(uni)
        if not src:
            continue                                # unknown token stays as written
        source, orig = src
        if source == QUESTION:
            if orig in question_map:
                values[uni] = question_map[orig]
        elif source:
            by_doc.setdefault(source, {})[orig] = uni
    for doc, origs in by_doc.items():
        for orig, val in decrypt(tenant_id, doc, list(origs)).items():
            values[origs[orig]] = val
    return _TOKEN.sub(lambda m: values.get(m.group(0), m.group(0)), answer), len(values)
