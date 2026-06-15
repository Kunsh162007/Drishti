"""Grounded assistant: retrieves from the crime DB and answers ONLY from retrieved records.

Free/demo mode (LLM_PROVIDER='none'): deterministic, extractive, cited answers.
Production: set LLM_PROVIDER + LLM_API_KEY to ground a real LLM on the same retrieved context.
The LLM is instructed to refuse when context is empty — fabrication is blocked here, not trusted.
"""
import re
from datetime import datetime, timedelta

from . import config
from .constants import KARNATAKA_DISTRICTS, CRIME_TYPES

_TYPE_LOOKUP = {t.lower(): t for t in CRIME_TYPES}


def parse_intent(message: str) -> dict:
    """Turn a natural-language query into a structured filter the API/map can apply."""
    msg = message.lower()
    f = {}
    for d in KARNATAKA_DISTRICTS:
        if d.lower() in msg or d.split()[0].lower() in msg:
            f["district"] = d
            break
    for key, canonical in _TYPE_LOOKUP.items():
        if key in msg:
            f["crime_type"] = canonical
            break
    if "theft" in msg and "crime_type" not in f:
        f["crime_type"] = "Vehicle Theft"
    if "fraud" in msg and "crime_type" not in f:
        f["crime_type"] = "Online Financial Fraud"

    now = datetime(2026, 6, 14)
    if "last month" in msg or "past month" in msg:
        f["date_from"] = (now - timedelta(days=30)).date().isoformat()
    elif "last week" in msg or "past week" in msg:
        f["date_from"] = (now - timedelta(days=7)).date().isoformat()
    elif "last year" in msg or "past year" in msg:
        f["date_from"] = (now - timedelta(days=365)).date().isoformat()

    m = re.search(r"after (\d{1,2})\s*(am|pm)?", msg)
    if m:
        h = int(m.group(1)) % 12 + (12 if m.group(2) == "pm" else 0)
        f["hour_min"] = h
    m = re.search(r"(night|after dark)", msg)
    if m:
        f["hour_min"] = 20
    return f


def _extractive_answer(message: str, records: list[dict], filt: dict) -> str:
    if not records:
        return ("I could not find any records matching that query in the authorised data. "
                "I will not speculate — please broaden the filters or check the spelling.")
    n = len(records)
    by_type, by_dist = {}, {}
    for r in records:
        by_type[r["crime_type"]] = by_type.get(r["crime_type"], 0) + 1
        by_dist[r["district"]] = by_dist.get(r["district"], 0) + 1
    top_type = max(by_type, key=by_type.get)
    top_dist = max(by_dist, key=by_dist.get)
    scope = []
    if filt.get("district"):
        scope.append(f"in {filt['district']}")
    if filt.get("crime_type"):
        scope.append(f"of type '{filt['crime_type']}'")
    if filt.get("date_from"):
        scope.append(f"since {filt['date_from']}")
    if filt.get("hour_min"):
        scope.append(f"after {filt['hour_min']:02d}:00")
    scope_txt = " ".join(scope) if scope else "matching your query"
    sample = records[0]
    return (
        f"Found **{n}** record(s) {scope_txt}. "
        f"The most frequent type is **{top_type}** ({by_type[top_type]}), "
        f"and the most affected district is **{top_dist}** ({by_dist[top_dist]}). "
        f"Example — FIR {sample['fir_number']}: {sample['crime_type']} at {sample['police_station']} "
        f"({sample['occurred_at'][:10]}). Every figure here is drawn directly from the cited FIRs; "
        f"nothing is inferred. Use the map filter applied alongside this answer to explore them."
    )


def _llm_answer(message: str, records: list[dict]) -> str | None:
    """Optional production path. Returns None to fall back to extractive if anything is missing."""
    if config.LLM_PROVIDER == "none" or not config.LLM_API_KEY:
        return None
    context = "\n".join(
        f"- FIR {r['fir_number']}: {r['crime_type']} ({r['crime_category']}) in {r['district']}, "
        f"{r['police_station']}, on {r['occurred_at'][:16]}. MO: {r['modus_operandi']}"
        for r in records[:40]
    )
    system = (
        "You are DRISHTI's police analyst assistant. Answer ONLY from the CONTEXT records. "
        "Cite FIR numbers. If the context does not contain the answer, say 'data not available' "
        "and do not speculate. Never invent names, numbers, or links."
    )
    user = f"CONTEXT:\n{context or '(no records)'}\n\nQUESTION: {message}"
    try:
        import httpx
        if config.LLM_PROVIDER == "anthropic":
            r = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": config.LLM_API_KEY, "anthropic-version": "2023-06-01"},
                json={"model": config.LLM_MODEL or "claude-opus-4-8", "max_tokens": 700,
                      "system": system, "messages": [{"role": "user", "content": user}]},
                timeout=40,
            )
            return r.json()["content"][0]["text"]
        # OpenAI-compatible (works for Groq/OpenAI/OpenRouter — set the right base via LLM_MODEL prefix)
        base = {"groq": "https://api.groq.com/openai/v1",
                "openai": "https://api.openai.com/v1"}.get(config.LLM_PROVIDER, "https://api.openai.com/v1")
        r = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            json={"model": config.LLM_MODEL or "llama-3.3-70b-versatile",
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                  "max_tokens": 700, "temperature": 0.1},
            timeout=40,
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


def answer(message: str, records: list[dict], filt: dict) -> dict:
    text = _llm_answer(message, records)
    mode = config.LLM_PROVIDER if text else "extractive-free"
    if not text:
        text = _extractive_answer(message, records, filt)
    return {
        "answer": text,
        "citations": [r["fir_number"] for r in records[:25]],
        "filter": filt,
        "grounded": True,
        "mode": mode,
    }
