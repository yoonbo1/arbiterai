"""Model calls via OpenAI-compatible endpoints (vLLM on a GPU box, Ollama on Apple Silicon).
Small tier by default, large tier only on escalation. Endpoints are local or BAA-covered."""
import os, re

import httpx

SMALL_URL = (os.environ.get("SMALL_MODEL_URL") or "http://vllm-small:8000/v1").rstrip("/")
SMALL_MODEL = os.environ.get("SMALL_MODEL") or "Qwen/Qwen2.5-7B-Instruct-AWQ"
# Escalation tier falls back to the small tier when unset. It must never default to the
# VLM: VLM_URL is empty on machines without one, and a VLM is not a text-reasoning model.
LARGE_URL = (os.environ.get("LARGE_MODEL_URL") or SMALL_URL).rstrip("/")
LARGE_MODEL = os.environ.get("LARGE_MODEL") or SMALL_MODEL
TIERS = {"small": (SMALL_URL, SMALL_MODEL), "large": (LARGE_URL, LARGE_MODEL)}
TIMEOUT = float(os.environ.get("LLM_TIMEOUT_S", "300"))
# Rough on-prem cost per 1k tokens (amortized GPU). Tune from your own metering.
COST_PER_1K = {"small": 0.0002, "large": 0.0015}

SYSTEM = ("You are a clinical documentation assistant. Answer ONLY from the provided excerpts. "
          "Cite each fact with the excerpt id in square brackets, e.g. [12]. Placeholders like "
          "<PERSON_1> are intentional; keep them exactly as written. If the excerpts do not "
          "contain the answer, say so.")

# Tested against qwen2.5:7b-instruct: a fully supported answer scores 1.0, an unsupported one
# 0.0 (a vaguer "fraction of claims" prompt scored a fully supported answer 0.5).
JUDGE = ("You are a strict fact checker. Compare ANSWER against CONTEXT. Output only one number: "
         "1.0 if every factual claim in ANSWER is stated in CONTEXT, 0.0 if none is, otherwise the "
         "fraction of claims that are. Ignore citation markers like [12] and placeholders like "
         "<PERSON_1>. No words, no explanation.")
_NUMBER = re.compile(r"\d*\.?\d+")


def total_tokens(j: dict) -> int:
    """usage.total_tokens is optional in OpenAI-compatible servers; Ollama sends it, others may
    send only prompt/completion counts or nothing."""
    u = j.get("usage") or {}
    t = u.get("total_tokens")
    if isinstance(t, int):
        return t
    return int(u.get("prompt_tokens") or 0) + int(u.get("completion_tokens") or 0)


def _chat(tier: str, messages: list[dict], max_tokens: int = 700) -> tuple[str, int]:
    url, model = TIERS[tier]
    r = httpx.post(f"{url}/chat/completions", timeout=TIMEOUT, json={
        "model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens})
    r.raise_for_status()
    j = r.json()
    return (j["choices"][0]["message"].get("content") or ""), total_tokens(j)


def answer(tier: str, question: str, chunks: list[dict]) -> tuple[str, int]:
    ctx = "\n\n".join(f"[{c['id']}] (p.{c['page']}, {c['section'] or 'n/a'}) {c['text']}" for c in chunks)
    return _chat(tier, [{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": f"Excerpts:\n{ctx}\n\nQuestion: {question}"}])


_CITE = re.compile(r"\s*\[\d+\]")


def faithfulness_score(answer_text: str, chunks: list[dict]) -> tuple[float, int]:
    """Cheap judge on the small model: fraction of answer claims supported by the excerpts.
    Returns (score, tokens_used) so judge calls are metered like answer calls.
    Citation markers are stripped first: the 7B judge scored "...is 9.0% [7]." as 0.0 and
    "...is 9.0%. [7]" as 1.0 on identical facts, discarding correct answers."""
    ctx = "\n".join(c["text"] for c in chunks)
    claim = _CITE.sub("", answer_text).strip()
    out, used = _chat("small", [
        {"role": "system", "content": JUDGE},
        {"role": "user", "content": f"CONTEXT:\n{ctx}\n\nANSWER:\n{claim}"}], max_tokens=8)
    m = _NUMBER.search(out)
    if not m:
        return 0.0, used
    v = float(m.group())
    if v > 1.0 and out.strip().endswith("%"):
        v /= 100.0
    return max(0.0, min(1.0, v)), used


def cost_cents(usage: dict) -> float:
    return sum(usage.get(t, 0) / 1000 * COST_PER_1K[t] for t in COST_PER_1K) * 100
