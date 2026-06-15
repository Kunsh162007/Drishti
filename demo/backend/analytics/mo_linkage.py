"""Modus-operandi (MO) crime linkage for DRISHTI.

Finds crimes with a similar method of operation to a target crime, combining:

* **TF-IDF + cosine similarity** (scikit-learn ``TfidfVectorizer``) over the
  ``modus_operandi`` free text, restricted to candidates in the same crime
  category as the target, and
* a **Jaccard token-overlap** signal that contributes interpretable
  ``shared_terms``.

The vectorizer is fit once on the candidate set for speed. Pure function:
target dict + list[dict] in -> list[dict] out. Robust to missing text.
"""
from __future__ import annotations

import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text):
    if not text:
        return set()
    return set(_TOKEN_RE.findall(str(text).lower()))


def link_by_mo(target: dict, records: list[dict], top_k: int) -> list[dict]:
    """Rank crimes by MO similarity to ``target`` (same-category candidates).

    Args:
        target: the crime dict to link from (must include ``fir_number``;
            ``modus_operandi`` may be empty).
        records: candidate crime dicts (typically pre-filtered to the target's
            ``crime_category`` by the caller).
        top_k: number of matches to return.

    Returns:
        ``[{fir_number, similarity, shared_terms[], ...all crime fields...}]``
        sorted by similarity desc, excluding the target FIR.
    """
    if not records:
        return []
    top_k = max(1, int(top_k or 1))
    target_fir = target.get("fir_number")
    target_text = target.get("modus_operandi") or ""

    # Candidate set excludes the target FIR.
    cands = [r for r in records if r.get("fir_number") != target_fir]
    if not cands:
        return []

    cand_texts = [(r.get("modus_operandi") or "") for r in cands]

    # Fit TF-IDF on candidate corpus once, then transform the target.
    try:
        vec = TfidfVectorizer(
            lowercase=True, stop_words="english", ngram_range=(1, 2),
            min_df=1, sublinear_tf=True,
        )
        cand_matrix = vec.fit_transform(cand_texts)
        tgt_vec = vec.transform([target_text])
        cos = cosine_similarity(tgt_vec, cand_matrix).ravel()
    except ValueError:
        # Empty vocabulary (all text blank) -> cosine contributes nothing.
        cos = np.zeros(len(cands))

    tgt_tokens = _tokens(target_text)

    out = []
    for i, r in enumerate(cands):
        toks = _tokens(cand_texts[i])
        shared = tgt_tokens & toks
        union = tgt_tokens | toks
        jacc = len(shared) / len(union) if union else 0.0
        # Blend cosine (semantic/weighted) with Jaccard (lexical overlap).
        sim = 0.7 * float(cos[i]) + 0.3 * jacc
        if sim <= 0:
            continue
        out.append({
            "fir_number": r.get("fir_number"),
            "similarity": round(float(sim), 3),
            "shared_terms": sorted(shared)[:10],
            **r,
        })

    out.sort(key=lambda x: -x["similarity"])
    return out[:top_k]
