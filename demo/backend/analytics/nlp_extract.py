"""Rule-based NLP over FIR narratives for DRISHTI.

Free, model-free information extraction from the ``modus_operandi`` +
``description`` free text of a crime. Uses regular expressions and small
curated lexicons (no heavy ML models, no network calls) to surface:

  * vehicle registrations, phone numbers, money amounts (regex),
  * weapons and entry/method keywords (lexicons),
  * candidate locations/landmarks (capitalised tokens near "near"/"at").

A separate :func:`corpus_keywords` helper computes TF-IDF top terms over a
collection of MO texts (scikit-learn) for corpus-level vocabulary.

Design rule (matches SPEC): NEVER invent. Only what is literally present in
the text is returned. Pure functions: dicts in -> JSON-serialisable out.
"""
from __future__ import annotations

import re
from collections import Counter

# --- regex patterns -----------------------------------------------------------
# Karnataka vehicle registration, tolerant of optional spaces/hyphens.
_VEHICLE_RE = re.compile(r"\bKA[\s-]?\d{2}[\s-]?[A-Z]{1,2}[\s-]?\d{3,4}\b", re.IGNORECASE)
# Indian mobile numbers: 10 digits starting 6-9, not part of a longer number.
_PHONE_RE = re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)")
# Money amounts: Rs / INR / rupee symbol followed by a number (with separators).
_MONEY_RE = re.compile(r"(?:Rs\.?|INR|₹)\s?\d[\d,]*(?:\.\d+)?", re.IGNORECASE)
# Capitalised landmark/location tokens following near/at/from/in.
_LOC_RE = re.compile(
    r"\b(?:near|at|from|in|opposite|behind|beside)\s+"
    r"((?:[A-Z][a-zA-Z]+)(?:\s+(?:[A-Z][a-zA-Z]+|Road|Layout|Nagar|Circle|"
    r"Market|Junction|Cross|Main|Temple|Park|Station|Mall|Bridge|Colony))*)"
)

# --- lexicons -----------------------------------------------------------------
_WEAPON_LEXICON = [
    "knife", "machete", "pistol", "firearm", "country-made", "country made",
    "revolver", "gun", "rifle", "acid", "iron rod", "rod", "sword", "dagger",
    "chopper", "sickle", "axe", "club", "stick", "blade", "chilli powder",
    "pepper spray", "syringe",
]
_METHOD_LEXICON = [
    "rear window", "lock broken", "broke the lock", "broken lock", "cut the lock",
    "otp", "phishing link", "phishing", "chain snatch", "chain snatching",
    "pillion rider", "pillion", "tailgating", "duplicate key", "master key",
    "scaling the wall", "wall scaling", "grill cut", "cut the grill",
    "impersonation", "fake call", "kyc update", "kyc fraud", "vishing",
    "sim swap", "card skimming", "skimming", "ransacked", "drugged", "sedated",
    "house break", "housebreak", "ventilator", "rooftop", "back door",
    "fake website", "uPI fraud", "upi", "qr code", "remote access", "anydesk",
    "screen sharing", "lottery scam", "job fraud", "matrimonial fraud",
    "investment fraud", "loan app", "sextortion", "snatched", "waylaid",
]

# Short stop-list for keyword extraction (kept tiny; sklearn used for corpus).
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "by", "for",
    "with", "was", "were", "is", "are", "be", "been", "from", "as", "that",
    "this", "it", "he", "she", "they", "his", "her", "their", "had", "has",
    "have", "who", "which", "when", "then", "but", "into", "out", "near",
    "after", "before", "complainant", "accused", "stated", "reported", "said",
    "victim", "person", "unknown", "one", "two", "approx", "approximately",
}
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z']+")


def _text_of(crime: dict) -> str:
    mo = crime.get("modus_operandi") or ""
    desc = crime.get("description") or ""
    return f"{mo} . {desc}".strip()


def _dedup(seq):
    seen = set()
    out = []
    for x in seq:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def _find_lexicon(text_low: str, lexicon: list[str]) -> list[str]:
    found = []
    for term in lexicon:
        if term.lower() in text_low:
            found.append(term)
    return _dedup(found)


def extract_entities(crime: dict, corpus_terms: list[str] | None = None) -> dict:
    """Extract grounded entities from a single crime's narrative text.

    Args:
        crime: crime dict; uses ``modus_operandi`` and ``description``.
        corpus_terms: optional corpus-level salient terms (e.g. from
            :func:`corpus_keywords`); when supplied, ``keywords`` is filtered
            to terms that appear in the corpus list, boosting relevance.

    Returns:
        ``{entities:{vehicles[],phones[],weapons[],methods[],amounts[],
        locations[]}, keywords:[...], summary:"..."}``. Only items literally
        present in the text are returned -- nothing is invented.
    """
    crime = crime or {}
    text = _text_of(crime)
    low = text.lower()

    # --- regex-based entities ---
    vehicles = _dedup(
        re.sub(r"[\s-]", "", m).upper() for m in _VEHICLE_RE.findall(text)
    )
    phones = _dedup(_PHONE_RE.findall(text))
    amounts = _dedup(m.strip() for m in _MONEY_RE.findall(text))

    locations = []
    for m in _LOC_RE.findall(text):
        loc = m.strip()
        # Drop trivial single common words mis-captured as a landmark.
        if loc and loc.lower() not in _STOP:
            locations.append(loc)
    locations = _dedup(locations)

    # --- lexicon-based entities ---
    weapons = _find_lexicon(low, _WEAPON_LEXICON)
    # weapon_used column is a grounded signal too (still "present" in record).
    wu = crime.get("weapon_used")
    if wu and str(wu).strip() and str(wu).lower() not in {"none", "nil", "na"}:
        weapons = _dedup([*weapons, str(wu).strip()])
    methods = _find_lexicon(low, _METHOD_LEXICON)

    # --- keyword extraction (frequency over non-stop words) ---
    words = [w.lower() for w in _WORD_RE.findall(text) if len(w) > 2]
    words = [w for w in words if w not in _STOP]
    freq = Counter(words)
    if corpus_terms:
        corpus_set = {t.lower() for t in corpus_terms}
        # Prefer corpus-salient terms; keep frequency order, then fill.
        salient = [w for w, _ in freq.most_common() if w in corpus_set]
        rest = [w for w, _ in freq.most_common() if w not in corpus_set]
        keywords = _dedup([*salient, *rest])[:8]
    else:
        keywords = [w for w, _ in freq.most_common(8)]

    summary = _summary(crime, vehicles, phones, weapons, methods, amounts, locations)

    return {
        "entities": {
            "vehicles": vehicles,
            "phones": phones,
            "weapons": weapons,
            "methods": methods,
            "amounts": amounts,
            "locations": locations,
        },
        "keywords": keywords,
        "summary": summary,
    }


def _summary(crime, vehicles, phones, weapons, methods, amounts, locations) -> str:
    """Deterministic one-line synopsis grounded only in extracted facts."""
    ctype = crime.get("crime_type") or "Incident"
    parts = [str(ctype)]
    if locations:
        parts.append(f"near {locations[0]}")
    if methods:
        parts.append(f"via {methods[0]}")
    if weapons:
        parts.append(f"weapon: {weapons[0]}")
    if vehicles:
        parts.append(f"vehicle {vehicles[0]}")
    if amounts:
        parts.append(f"amount {amounts[0]}")
    if phones:
        parts.append(f"phone {phones[0]}")
    text = " | ".join(parts)
    # If nothing extracted beyond the type, say so plainly.
    if len(parts) == 1:
        return f"{ctype}: no structured entities extracted from narrative."
    return text


def corpus_keywords(crimes: list[dict], top_n: int = 25) -> list[str]:
    """TF-IDF top terms over the MO/description corpus (helper).

    Args:
        crimes: list of crime dicts.
        top_n: number of top terms to return.

    Returns:
        ``[term, ...]`` of length <= ``top_n`` ranked by summed TF-IDF weight.
        Returns ``[]`` if the corpus is empty / all-blank.
    """
    if not crimes:
        return []
    top_n = max(1, int(top_n or 1))
    texts = [_text_of(c) for c in crimes]
    texts = [t for t in texts if t and t.strip(" .")]
    if not texts:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(
            lowercase=True, stop_words="english", ngram_range=(1, 2),
            min_df=1, max_features=2000, sublinear_tf=True,
        )
        m = vec.fit_transform(texts)
    except ValueError:
        return []
    import numpy as np
    weights = np.asarray(m.sum(axis=0)).ravel()
    terms = vec.get_feature_names_out()
    order = np.argsort(-weights)
    out = []
    for i in order:
        term = str(terms[i])
        if term in _STOP or term.isdigit():
            continue
        out.append(term)
        if len(out) >= top_n:
            break
    return out
