"""Grounded assistant: retrieves from the crime DB and answers ONLY from retrieved records.

Free/demo mode (LLM_PROVIDER='none'): deterministic, extractive, cited answers.
Production: set LLM_PROVIDER + LLM_API_KEY to ground a real LLM on the same retrieved context.
The LLM is instructed to refuse when context is empty — fabrication is blocked here, not trusted.
"""
import re
from datetime import datetime, timedelta

from . import config
from .constants import KARNATAKA_DISTRICTS

# ---------------------------------------------------------------------------
# Semantic vocabularies — map how officers actually phrase things to the exact
# canonical values stored in the DB. Substring/keyword matching alone missed
# colloquial names (Bangalore→Bengaluru City), historical district names
# (Gulbarga→Kalaburagi), and crime slang (chain snatch, OTP scam, break-in).
# ---------------------------------------------------------------------------

# Colloquial / historical / abbreviated district names -> canonical KSP district.
_DISTRICT_ALIASES = {
    "bengaluru rural": "Bengaluru Rural", "bangalore rural": "Bengaluru Rural",
    "bengaluru city": "Bengaluru City", "bangalore city": "Bengaluru City",
    "bengaluru": "Bengaluru City", "bangalore": "Bengaluru City", "blr": "Bengaluru City",
    "capital": "Bengaluru City", "silicon city": "Bengaluru City",
    "mysore": "Mysuru", "mangalore": "Mangaluru",
    "hubli": "Hubballi-Dharwad", "hubballi": "Hubballi-Dharwad", "dharwad": "Hubballi-Dharwad",
    "belgaum": "Belagavi", "gulbarga": "Kalaburagi", "bellary": "Ballari",
    "bijapur": "Vijayapura", "shimoga": "Shivamogga", "tumkur": "Tumakuru",
    "chikmagalur": "Chikkamagaluru", "chickballapur": "Chikkaballapura",
    "davangere": "Davanagere", "bagalkot": "Bagalkote", "chamrajnagar": "Chamarajanagar",
    "ramanagaram": "Ramanagara", "karwar": "Uttara Kannada", "dk": "Dakshina Kannada",
}
# Add every canonical district (and its first token) as a self-alias.
for _d in KARNATAKA_DISTRICTS:
    _DISTRICT_ALIASES.setdefault(_d.lower(), _d)
# Longest alias first so "bengaluru rural" wins over "bengaluru".
_DISTRICT_ITEMS = sorted(_DISTRICT_ALIASES.items(), key=lambda kv: -len(kv[0]))

# Crime slang / synonyms -> canonical crime_type (as seeded in the DB).
# Order matters: more specific phrases must precede generic ones.
_CRIME_SYNONYMS = [
    (["chain snatch", "snatching", "snatch"], "Chain Snatching"),
    (["attempt to murder", "attempted murder", "attempt murder"], "Attempt to Murder"),
    (["armed robbery", "gunpoint", "gun point", "armed loot"], "Armed Robbery"),
    (["robbery with grievous", "grievous hurt robbery"], "Robbery with Grievous Hurt"),
    (["dacoity", "gang robbery"], "Dacoity"),
    (["extortion", "ransom", "protection money"], "Extortion"),
    (["robber", "robbed", "looted", "loot", "mugging", "mugged"], "Robbery"),
    (["vehicle theft", "bike theft", "car theft", "stolen vehicle", "stolen bike",
      "stolen car", "motorcycle theft", "two-wheeler theft", "two wheeler theft",
      "auto theft", "vehicle stolen"], "Vehicle Theft"),
    (["house theft", "home theft"], "House Theft"),
    (["burglar", "house break", "housebreaking", "break-in", "break in", "burgle"], "Burglary"),
    (["petty theft", "pickpocket", "pick-pocket", "minor theft"], "Petty Theft"),
    (["upi fraud", "upi scam"], "UPI Fraud"),
    (["otp fraud", "otp scam", "phishing"], "Phishing / OTP Fraud"),
    (["investment fraud", "investment scam", "ponzi", "trading scam"], "Investment Fraud"),
    (["online financial fraud", "online fraud", "online scam", "internet fraud",
      "cyber fraud", "digital fraud"], "Online Financial Fraud"),
    (["cheating", "cheated"], "Cheating / Fraud"),
    (["murder", "homicide", "killed", "killing"], "Murder"),
    (["assault", "attacked", "beaten up", "physical attack"], "Assault"),
    (["illicit liquor", "illegal liquor", "excise", "hooch"], "Excise / Illicit Liquor"),
    (["drug", "narcotic", "ganja", "ndps", "peddl", "cocaine", "heroin", "mdma", "weed"],
     "Drug Possession (NDPS)"),
    (["kidnap", "abduct"], "Kidnapping"),
    (["missing person", "missing people", "gone missing", "disappeared"], "Missing Person"),
    (["molest", "eve tease", "eve-teas", "outrage.* modesty"], "Molestation"),
    (["dowry"], "Dowry Harassment"),
    (["domestic violence", "domestic abuse", "wife beating"], "Domestic Violence"),
    (["pocso", "child sexual", "child abuse"], "POCSO"),
    (["riot", "mob violence", "unlawful assembly"], "Rioting"),
]

# Category-level phrases -> canonical crime_category. Applied only when no
# specific crime_type matched, so "violent crime in Mysore" broadens correctly.
_CATEGORY_SYNONYMS = [
    (["violent crime", "violent crimes", "violence", "violent"], "Violent"),
    (["property crime", "property crimes", "property offence"], "Property"),
    (["cybercrime", "cyber crime", "cyber", "online crime", "digital crime"], "Cybercrime"),
    (["economic offence", "economic crime", "financial crime", "white collar", "white-collar"],
     "Economic"),
    (["narcotics", "drug crime", "drug crimes"], "Narcotics"),
    (["crime against women", "against women", "women safety", "women-related"], "Crime Against Women"),
    (["crime against children", "against children", "child crime"], "Crime Against Children"),
]


def _match(msg: str, items) -> str | None:
    """First canonical whose any alias appears in msg.

    Leading word-boundary only (no trailing boundary) so the alias also matches
    plurals and inflections — "murders", "OTP scams", "burglaries", "kidnapped".
    The leading \\b still prevents mid-word hits (e.g. "riot" inside "patriot").
    """
    for aliases, canonical in items:
        for a in aliases:
            if re.search(r"\b" + a, msg):
                return canonical
    return None


def _match_district(msg: str) -> str | None:
    for alias, canonical in _DISTRICT_ITEMS:
        if re.search(r"\b" + re.escape(alias) + r"\b", msg):
            return canonical
    return None


def _parse_dates(msg: str, f: dict) -> None:
    now = datetime.now()
    m = re.search(r"last\s+(\d{1,3})\s*(day|week|month|year)s?", msg)
    if m:
        n = int(m.group(1)); unit = m.group(2)
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
        f["date_from"] = (now - timedelta(days=days)).date().isoformat()
        return
    if re.search(r"\b(last|past)\s+month\b", msg) or "recent" in msg or "lately" in msg or "nowadays" in msg:
        f["date_from"] = (now - timedelta(days=30)).date().isoformat(); return
    if re.search(r"\b(last|past)\s+week\b", msg):
        f["date_from"] = (now - timedelta(days=7)).date().isoformat(); return
    if re.search(r"\b(last|past)\s+year\b", msg):
        f["date_from"] = (now - timedelta(days=365)).date().isoformat(); return
    if "yesterday" in msg:
        f["date_from"] = (now - timedelta(days=1)).date().isoformat(); return
    if "today" in msg:
        f["date_from"] = now.date().isoformat(); return
    if "this year" in msg:
        f["date_from"] = f"{now.year}-01-01"; return
    ym = re.search(r"\b(in|during|for)?\s*(20[12][0-9])\b", msg)
    if ym:
        yr = ym.group(2)
        f["date_from"] = f"{yr}-01-01"; f["date_to"] = f"{yr}-12-31"


def parse_intent(message: str) -> dict:
    """Turn a natural-language query into a structured filter the API/map can apply.

    Semantic layer: resolves colloquial district names, crime slang/synonyms,
    category-level asks, and a range of date/time phrasings to the canonical
    values stored in the DB — so intent survives paraphrasing.
    """
    msg = (message or "").lower()
    f = {}

    district = _match_district(msg)
    if district:
        f["district"] = district

    crime_type = _match(msg, _CRIME_SYNONYMS)
    if crime_type:
        f["crime_type"] = crime_type
    else:
        category = _match(msg, _CATEGORY_SYNONYMS)
        if category:
            f["category"] = category
        elif re.search(r"\b(theft|stolen|stealing|robber|loot)", msg):
            f["category"] = "Property"
        elif re.search(r"\b(fraud|scam|cyber)", msg):
            f["category"] = "Cybercrime"

    _parse_dates(msg, f)

    m = re.search(r"after (\d{1,2})\s*(am|pm)?", msg)
    if m:
        f["hour_min"] = int(m.group(1)) % 12 + (12 if m.group(2) == "pm" else 0)
    if re.search(r"\b(night|after dark|late night|midnight)\b", msg):
        f["hour_min"] = 20

    # Explicit quoted phrase -> free-text search over MO / description / station.
    q = re.search(r'"([^"]{2,})"', message or "")
    if q:
        f["q"] = q.group(1)
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
    if filt.get("category"):
        scope.append(f"in category '{filt['category']}'")
    if filt.get("date_from"):
        scope.append(f"since {filt['date_from']}")
    if filt.get("date_to"):
        scope.append(f"up to {filt['date_to']}")
    if filt.get("q"):
        scope.append(f"matching \"{filt['q']}\"")
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
