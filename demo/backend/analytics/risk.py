"""Place-based risk scoring for DRISHTI.

This module produces an EXPLAINABLE, PLACE-BASED risk score per H3 hexagon
for operational decision-support (e.g. patrol allocation). It is deliberately
NOT a person-level prediction: it scores *locations*, never individuals, and
exposes plain-language ``drivers`` for every score so an officer can see why
a hex is rated as it is. This avoids the well-known fairness pitfalls of
individual-level predictive policing.

Score = normalised blend of:
  * recency-weighted incident density (recent incidents weigh more),
  * night-time share (incidents occurring 20:00-05:59), and
  * mean severity.

Pure function: list[dict] in -> list[dict] out. Robust to missing fields.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

try:
    import h3
except Exception:  # pragma: no cover
    h3 = None


def _ordinal(iso):
    if not iso:
        return None
    try:
        from datetime import date
        y, m, d = (int(x) for x in str(iso)[:10].split("-")[:3])
        return date(y, m, d).toordinal()
    except Exception:
        return None


def _centroid(idx, lat, lng):
    if h3 and idx:
        try:
            a, b = h3.cell_to_latlng(idx)
            return float(a), float(b)
        except Exception:
            pass
    try:
        return (float(lat), float(lng)) if lat is not None else (None, None)
    except Exception:
        return None, None


def risk_scores(records: list[dict], resolution: int) -> list[dict]:
    """Compute place-based, explainable risk per H3 cell.

    Args:
        records: crime dicts with ``h3_r{resolution}``, ``occurred_at``,
            ``hour``, ``severity`` (any may be missing/None).
        resolution: H3 resolution (7, 8 or 9).

    Returns:
        ``[{h3, lat, lng, risk, drivers[]}]`` sorted by risk desc. ``risk`` is
        in [0,1]; ``drivers`` are plain-language reasons. Place-based only.
    """
    col = f"h3_r{resolution}" if resolution in (7, 8, 9) else "h3_r8"

    # Establish the recency reference (most recent date seen).
    all_ords = [o for o in (_ordinal(r.get("occurred_at")) for r in records) if o is not None]
    latest = max(all_ords) if all_ords else None
    half_life = 180.0  # days; weight halves every ~6 months

    cells = defaultdict(lambda: {
        "w": 0.0, "n": 0, "night": 0, "sev_sum": 0.0, "sev_n": 0,
        "lat": None, "lng": None, "types": defaultdict(int),
    })

    for r in records:
        idx = r.get(col)
        if not idx:
            continue
        c = cells[idx]
        c["n"] += 1
        if c["lat"] is None:
            c["lat"], c["lng"] = r.get("latitude"), r.get("longitude")

        # recency weight
        o = _ordinal(r.get("occurred_at"))
        if o is not None and latest is not None:
            age = max(0, latest - o)
            c["w"] += 0.5 ** (age / half_life)
        else:
            c["w"] += 0.5  # unknown date -> modest weight

        # night share
        h = r.get("hour")
        try:
            h = int(h) if h is not None else None
        except Exception:
            h = None
        if h is not None and (h >= 20 or h <= 5):
            c["night"] += 1

        # severity
        try:
            sv = float(r.get("severity")) if r.get("severity") is not None else None
        except Exception:
            sv = None
        if sv is not None:
            c["sev_sum"] += sv
            c["sev_n"] += 1

        ct = r.get("crime_type")
        if ct:
            c["types"][ct] += 1

    if not cells:
        return []

    # Normalisers across cells.
    max_w = max(c["w"] for c in cells.values()) or 1.0

    out = []
    for idx, c in cells.items():
        density = c["w"] / max_w                       # 0-1 recency-weighted density
        night_share = c["night"] / c["n"] if c["n"] else 0.0
        mean_sev = (c["sev_sum"] / c["sev_n"]) if c["sev_n"] else 3.0
        sev_norm = max(0.0, min(1.0, (mean_sev - 1.0) / 4.0))  # severity 1-5 -> 0-1

        risk = 0.5 * density + 0.25 * night_share + 0.25 * sev_norm
        risk = round(float(max(0.0, min(1.0, risk))), 3)

        drivers = []
        if density > 0.6:
            drivers.append("high recent incident density")
        elif density > 0.3:
            drivers.append("moderate recent incident density")
        if night_share > 0.4:
            drivers.append(f"{round(night_share * 100)}% of incidents occur at night")
        if sev_norm > 0.6:
            drivers.append(f"high average severity ({mean_sev:.1f}/5)")
        if c["types"]:
            top_type = max(c["types"].items(), key=lambda kv: kv[1])[0]
            drivers.append(f"recurring {top_type}")
        if not drivers:
            drivers.append("low overall activity")

        lat, lng = _centroid(idx, c["lat"], c["lng"])
        out.append({
            "h3": idx,
            "lat": lat,
            "lng": lng,
            "risk": risk,
            "drivers": drivers,
        })

    out.sort(key=lambda x: -x["risk"])
    return out
