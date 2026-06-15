"""Fairness / accountability diagnostics for DRISHTI.

Produces *recording-coverage* diagnostics over the crime corpus: how records
are distributed across districts and which categories dominate where. These
are decision-support diagnostics to prompt review -- they are emphatically
NOT proof of bias. Skewed record shares can equally reflect genuine crime
differences, population density, reporting culture, or station resourcing.
Treat every flag as a question to investigate, not a verdict.

Pure function: list[dict] in -> JSON-serialisable dict out. Robust to missing
fields.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np


def fairness_metrics(crimes: list[dict]) -> dict:
    """District coverage, category mix, and outlier/concentration flags.

    Args:
        crimes: list of crime dicts.

    Returns:
        ``{coverage_by_district:[{name, records, share_pct}],
        category_mix:[{district, top_category, share}],
        disparity_flags:[{type, detail}]}``.

    NOTE: these are recording-coverage diagnostics, not proof of bias. A flag
    means "this distribution is unusual -- review why", not "this is unfair".
    """
    crimes = crimes or []
    total = len(crimes)
    if total == 0:
        return {"coverage_by_district": [], "category_mix": [], "disparity_flags": []}

    by_district = defaultdict(int)
    cat_by_district = defaultdict(lambda: defaultdict(int))
    for c in crimes:
        d = c.get("district")
        if not d:
            continue
        by_district[d] += 1
        cat = c.get("crime_category")
        if cat:
            cat_by_district[d][cat] += 1

    if not by_district:
        return {"coverage_by_district": [], "category_mix": [], "disparity_flags": []}

    # --- coverage by district ---
    coverage = [
        {"name": d, "records": n, "share_pct": round(100.0 * n / total, 2)}
        for d, n in sorted(by_district.items(), key=lambda kv: -kv[1])
    ]

    # --- category mix (dominant category per district) ---
    category_mix = []
    for d, cats in cat_by_district.items():
        dn = by_district[d]
        if not cats or dn == 0:
            continue
        top_cat, top_n = max(cats.items(), key=lambda kv: kv[1])
        category_mix.append({
            "district": d,
            "top_category": top_cat,
            "share": round(top_n / dn, 3),
        })
    category_mix.sort(key=lambda x: -x["share"])

    # --- disparity flags ---
    flags = []
    counts = np.array([n for _, n in by_district.items()], dtype=float)
    names = list(by_district.keys())
    mean = float(counts.mean())
    std = float(counts.std())

    # Outlier districts by record share (z-score on counts). Honest framing.
    if std > 0:
        for name, n in zip(names, counts):
            z = (n - mean) / std
            if z >= 2.0:
                flags.append({
                    "type": "high_coverage_outlier",
                    "detail": (f"{name} holds {round(100.0 * n / total, 1)}% of records "
                               f"(z={z:.1f}) -- review whether this reflects true crime "
                               f"volume, population, or over-recording."),
                })
            elif z <= -1.5 and n > 0:
                flags.append({
                    "type": "low_coverage_outlier",
                    "detail": (f"{name} holds only {round(100.0 * n / total, 1)}% of records "
                               f"(z={z:.1f}) -- review for possible under-recording or "
                               f"genuinely low incidence."),
                })

    # Category over-concentration within a district.
    for m in category_mix:
        if m["share"] >= 0.6 and by_district[m["district"]] >= 10:
            flags.append({
                "type": "category_concentration",
                "detail": (f"{m['district']}: {round(m['share'] * 100)}% of records are "
                           f"'{m['top_category']}' -- review whether recording is "
                           f"narrowly focused on one category."),
            })

    return {
        "coverage_by_district": coverage,
        "category_mix": category_mix,
        "disparity_flags": flags,
    }
