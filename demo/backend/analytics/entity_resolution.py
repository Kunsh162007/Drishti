"""Entity resolution (identity de-duplication) for DRISHTI.

Standard record-linkage pipeline:

1. **Blocking** -- candidate pairs are generated only within blocks
   (first token of the normalized name, a coarse phonetic key, and shared
   phone number) to avoid the O(n^2) all-pairs comparison on large inputs.
2. **Scoring** -- each candidate pair is scored with RapidFuzz
   (``token_sort_ratio`` + Jaro-Winkler), with a strong boost when the phone
   number matches exactly.
3. **Decision** -- auto / review / reject thresholds, kept explainable via
   per-pair ``evidence`` strings.

Surfaces planted name-variant duplicates (e.g. "Ravi Kumar" vs "Kumar Ravi"
vs "Ravi Kumar S"). Pure function: list[dict] in -> list[dict] out.
"""
from __future__ import annotations

import re
from collections import defaultdict

from rapidfuzz import fuzz, distance


def _norm(s):
    if not s:
        return ""
    s = str(s).lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _phonetic_key(name: str) -> str:
    """Cheap Soundex-like key on the first token (vowel-strip + collapse).

    Not a full Soundex, but groups common transliteration variants well
    enough for blocking (e.g. 'kumar'/'kumaar' -> same key).
    """
    if not name:
        return ""
    tok = name.split()[0]
    head = tok[0]
    rest = re.sub(r"[aeiou]", "", tok[1:])
    rest = re.sub(r"(.)\1+", r"\1", rest)  # collapse repeats
    return (head + rest)[:5]


def _norm_phone(p):
    if not p:
        return ""
    digits = re.sub(r"\D", "", str(p))
    return digits[-10:] if len(digits) >= 10 else digits


def resolve_entities(persons: list[dict], threshold: float) -> list[dict]:
    """Resolve likely-duplicate person identities via blocking + fuzzy match.

    Args:
        persons: person dicts (``full_name``, ``normalized_name``, ``phone``,
            ``fir_number``, ``person_id`` ...). Any field may be missing/None.
        threshold: minimum similarity (0-1) for a pair to be returned as
            'review'. Pairs >= 0.95 or with a phone match are 'auto'.

    Returns:
        ``[{a, b, a_fir, b_fir, score, evidence[], decision}]`` sorted by
        score desc. 'reject' pairs are excluded.
    """
    if not persons:
        return []
    threshold = float(threshold) if threshold is not None else 0.82

    # Pre-compute normalised fields once.
    P = []
    for p in persons:
        name = _norm(p.get("normalized_name") or p.get("full_name"))
        P.append({
            "pid": p.get("person_id"),
            "fir": p.get("fir_number"),
            "name_raw": p.get("full_name") or p.get("normalized_name") or "",
            "name": name,
            "phone": _norm_phone(p.get("phone")),
            "district": p.get("district"),
        })

    # ---- blocking --------------------------------------------------------
    blocks = defaultdict(list)
    for i, p in enumerate(P):
        if not p["name"]:
            continue
        first = p["name"].split()[0]
        blocks[("first", first)].append(i)
        blocks[("phon", _phonetic_key(p["name"]))].append(i)
        if p["phone"]:
            blocks[("phone", p["phone"])].append(i)

    seen_pairs = set()
    results = []

    for key, members in blocks.items():
        if len(members) < 2 or len(members) > 2000:
            # Skip degenerate / pathological blocks (e.g. all-empty key).
            if len(members) > 2000:
                continue
            continue
        for a_i in range(len(members)):
            for b_i in range(a_i + 1, len(members)):
                i, j = members[a_i], members[b_i]
                a, b = P[i], P[j]
                if a["fir"] == b["fir"] and a["pid"] == b["pid"]:
                    continue
                pk = tuple(sorted((str(a["pid"]), str(b["pid"]))))
                if pk in seen_pairs:
                    continue
                seen_pairs.add(pk)

                if not a["name"] or not b["name"]:
                    continue

                tsr = fuzz.token_sort_ratio(a["name"], b["name"]) / 100.0
                jw = distance.JaroWinkler.normalized_similarity(a["name"], b["name"])
                score = 0.6 * tsr + 0.4 * jw

                phone_match = bool(a["phone"]) and a["phone"] == b["phone"]
                if phone_match:
                    score = max(score, 0.9) + 0.05 * (1 - max(score, 0.9))
                    score = min(1.0, max(score, 0.95))

                evidence = [
                    f"token_sort_ratio={tsr:.2f}",
                    f"jaro_winkler={jw:.2f}",
                ]
                if phone_match:
                    evidence.append(f"identical phone ({a['phone']})")
                if a["district"] and a["district"] == b["district"]:
                    evidence.append("same district")

                if score >= 0.95 or phone_match:
                    decision = "auto"
                elif score >= threshold:
                    decision = "review"
                else:
                    continue  # reject -> excluded

                results.append({
                    "a": a["name_raw"],
                    "b": b["name_raw"],
                    "a_fir": a["fir"],
                    "b_fir": b["fir"],
                    "score": round(float(score), 3),
                    "evidence": evidence,
                    "decision": decision,
                })

    results.sort(key=lambda x: -x["score"])
    return results
