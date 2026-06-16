"""Behavioral Analytics for repeat offenders — DRISHTI.

Builds a criminal career profile for a named suspect:
  - Full chronological crime timeline
  - Crime type diversity (Shannon entropy)
  - Geographic drift (centroid displacement over time)
  - Co-offender frequency map
  - Recidivism risk scoring (simplified RNR-inspired static factors)
  - Escalation detection (severity trend via least-squares)

Academic basis:
  Andrews DA & Bonta J (2010). The psychology of criminal conduct. 5th ed.
  Farrington DP (1992). Criminal career research in the United Kingdom.
    British Journal of Criminology 32:521-536.
  Coid JW et al. (2009). Predicting and understanding risk of reoffending.
    Ministry of Justice Research Series 6/09.

Pure function. Standard library only.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict


def _date_ord(s: str) -> int:
    try:
        parts = re.split(r"[-T/ ]", str(s or ""))
        return int(parts[0]) * 10000 + int(parts[1]) * 100 + int(parts[2])
    except Exception:
        return 0


def _entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counts if c > 0)


def _linreg_slope(ys: list[float]) -> float:
    """Return slope of least-squares line through ys (0,1,2,...)."""
    n = len(ys)
    if n < 2:
        return 0.0
    sx = n * (n - 1) / 2
    sxx = n * (n - 1) * (2 * n - 1) / 6
    sy = sum(ys)
    sxy = sum(i * y for i, y in enumerate(ys))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-9:
        return 0.0
    return (n * sxy - sx * sy) / denom


def criminal_profile(
    crimes: list[dict],
    persons: list[dict],
    target_name: str,
    *,
    top_co_offenders: int = 10,
) -> dict:
    """Build a full behavioral profile for ``target_name``.

    Args:
        crimes: all Crime records as dicts.
        persons: all Person records as dicts.
        target_name: partial name to match (case-insensitive).
        top_co_offenders: how many co-offenders to surface.

    Returns:
        Behavioral profile dict.
    """
    target_lower = target_name.lower().strip()
    _tokens = [t for t in target_lower.split() if len(t) > 1]

    def _matches(p: dict) -> bool:
        if not _tokens:
            return False
        name = (p.get("full_name") or "").lower()
        norm = (p.get("normalized_name") or "").lower()
        return all(tok in name or tok in norm for tok in _tokens)

    # ── Find FIRs linked to target ────────────────────────────────────────────
    person_rows = [p for p in persons if _matches(p)]
    if not person_rows:
        return {"found": False, "name": target_name, "firs": [], "timeline": [],
                "risk_score": 0, "risk_label": "Unknown", "summary": "No matching person found."}

    # Canonical name = most common among matches
    name_counts: Counter = Counter(p.get("full_name", "") for p in person_rows)
    canonical_name = name_counts.most_common(1)[0][0]

    true_ids = {p.get("true_identity_id") or p.get("person_id", "") for p in person_rows}
    fir_numbers = {p.get("fir_number", "") for p in person_rows if p.get("fir_number")}

    # All FIRs for any alias of this person
    alias_rows = [p for p in persons if (p.get("true_identity_id") or p.get("person_id", "")) in true_ids]
    for ar in alias_rows:
        if ar.get("fir_number"):
            fir_numbers.add(ar.get("fir_number"))

    aliases = sorted({p.get("full_name", "") for p in alias_rows} - {canonical_name})

    # ── Build timeline ────────────────────────────────────────────────────────
    fir_map = {c.get("fir_number"): c for c in crimes if c.get("fir_number") in fir_numbers}
    timeline = sorted(fir_map.values(), key=lambda c: _date_ord(c.get("occurred_at")))

    if not timeline:
        return {"found": False, "name": canonical_name, "firs": [], "timeline": [],
                "risk_score": 0, "risk_label": "Unknown", "summary": "Person found but no linked crime records."}

    # ── Type diversity ────────────────────────────────────────────────────────
    type_counts: Counter = Counter(c.get("crime_type", "Unknown") for c in timeline)
    diversity_entropy = round(_entropy(list(type_counts.values())), 3)

    # ── Geographic drift (centroid of first half vs second half) ──────────────
    geo_crimes = [c for c in timeline if c.get("latitude") and c.get("longitude")]
    geo_drift_km = None
    if len(geo_crimes) >= 4:
        mid = len(geo_crimes) // 2
        def centroid(lst):
            return (sum(float(c["latitude"]) for c in lst) / len(lst),
                    sum(float(c["longitude"]) for c in lst) / len(lst))
        c1 = centroid(geo_crimes[:mid])
        c2 = centroid(geo_crimes[mid:])
        R = 6371.0
        dlat = math.radians(c2[0] - c1[0])
        dlng = math.radians(c2[1] - c1[1])
        a = math.sin(dlat/2)**2 + math.cos(math.radians(c1[0]))*math.cos(math.radians(c2[0]))*math.sin(dlng/2)**2
        geo_drift_km = round(R * 2 * math.asin(math.sqrt(max(0, a))), 2)

    # ── Co-offenders ──────────────────────────────────────────────────────────
    co_counter: Counter = Counter()
    for fir in fir_numbers:
        for p in persons:
            if p.get("fir_number") == fir and (p.get("true_identity_id") or "") not in true_ids:
                co_counter[p.get("full_name", "Unknown")] += 1
    top_co = [{"name": n, "shared_firs": v} for n, v in co_counter.most_common(top_co_offenders)]

    # ── Escalation: severity trend ────────────────────────────────────────────
    sevs = [float(c.get("severity") or 0) for c in timeline]
    severity_slope = round(_linreg_slope(sevs), 4) if len(sevs) >= 3 else 0.0
    if severity_slope > 0.15:
        escalation = "escalating"
    elif severity_slope < -0.15:
        escalation = "de-escalating"
    else:
        escalation = "stable"

    # ── Recidivism risk score (simplified static factors, 0-100) ─────────────
    # Factors: count, diversity, recency, severity level, co-offender breadth, weapon use
    count_f = min(len(timeline) / 10.0, 1.0) * 30          # max 30 pts
    diversity_f = min(diversity_entropy / 3.0, 1.0) * 20    # max 20 pts
    recency_f = 0.0
    last_ord = _date_ord(timeline[-1].get("occurred_at", ""))
    today_approx = 2026 * 10000 + 100
    if last_ord and today_approx - last_ord < 365:
        recency_f = 20.0
    elif last_ord and today_approx - last_ord < 365 * 2:
        recency_f = 10.0
    severity_f = min((sum(sevs) / max(1, len(sevs))) / 5.0, 1.0) * 15  # max 15 pts
    co_f = min(len(co_counter) / 20.0, 1.0) * 10               # max 10 pts
    weapon_f = 5.0 if any(c.get("weapon_used") for c in timeline) else 0.0
    risk_score = round(count_f + diversity_f + recency_f + severity_f + co_f + weapon_f)
    if risk_score >= 65:
        risk_label = "High"
    elif risk_score >= 35:
        risk_label = "Medium"
    else:
        risk_label = "Low"

    # ── District breakdown ────────────────────────────────────────────────────
    district_counts: Counter = Counter(c.get("district", "Unknown") for c in timeline)

    # ── Monthly activity ──────────────────────────────────────────────────────
    month_counts: Counter = Counter()
    for c in timeline:
        d = str(c.get("occurred_at") or "")
        if len(d) >= 7:
            month_counts[d[:7]] += 1

    return {
        "found": True,
        "name": canonical_name,
        "aliases": aliases,
        "fir_count": len(timeline),
        "timeline": timeline,
        "type_distribution": dict(type_counts.most_common()),
        "diversity_entropy": diversity_entropy,
        "district_distribution": dict(district_counts.most_common()),
        "monthly_activity": dict(sorted(month_counts.items())),
        "geo_drift_km": geo_drift_km,
        "top_co_offenders": top_co,
        "severity_slope": severity_slope,
        "escalation": escalation,
        "risk_score": risk_score,
        "risk_label": risk_label,
        "risk_factors": {
            "criminal_count": round(count_f),
            "type_diversity": round(diversity_f),
            "recency": round(recency_f),
            "severity_level": round(severity_f),
            "network_breadth": round(co_f),
            "weapon_use": round(weapon_f),
        },
        "summary": (
            f"{canonical_name} has {len(timeline)} linked crime record(s) across "
            f"{len(district_counts)} district(s). "
            f"Offense diversity entropy: {diversity_entropy:.2f}. "
            f"Severity trend: {escalation}. "
            f"Recidivism risk: {risk_label} ({risk_score}/100)."
        ),
    }
