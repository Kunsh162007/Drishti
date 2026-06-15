"""Spatial hotspot analytics for DRISHTI.

Implements two grounded methods over H3 hexagonal cells:

* ``compute_hotspots``  -- Getis-Ord Gi* local statistic (Ord & Getis 1995).
  For each cell we compute a local sum over its H3 k-ring neighbourhood
  (``h3.grid_disk``) and standardise it against the global mean/variance to
  obtain a z-score (the Gi* statistic). Significant high-value clusters are
  'hot', significant low-value clusters are 'cold'.

* ``emerging_hotspots`` -- Emerging Hot Spot Analysis (ESRI/ArcGIS style).
  Each cell's recent window is compared against its historical baseline and
  classified as new / intensifying / persistent / diminishing / sporadic.

Pure functions: list[dict] in -> list[dict] out. Robust to missing fields.
Falls back to a global z-score if the ``h3`` library is unavailable.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

try:
    import h3
except Exception:  # pragma: no cover
    h3 = None


def _norm_sf(z: float) -> float:
    """Two-sided significance in [0,1] from a z-score via the normal CDF.

    Uses ``math.erf`` so we don't need scipy. Returns P(|Z| <= |z|), i.e.
    higher = more significant. Caps the practical range at ~3.5 sigma.
    """
    if z is None or math.isnan(z):
        return 0.0
    a = abs(float(z))
    # P(|Z| <= a) = erf(a / sqrt(2))
    return float(max(0.0, min(1.0, math.erf(a / math.sqrt(2.0)))))


def _centroid(idx, fallback_lat=None, fallback_lng=None):
    if h3 and idx:
        try:
            lat, lng = h3.cell_to_latlng(idx)
            return float(lat), float(lng)
        except Exception:
            pass
    if fallback_lat is not None and fallback_lng is not None:
        try:
            return float(fallback_lat), float(fallback_lng)
        except Exception:
            return None, None
    return None, None


def compute_hotspots(records: list[dict], resolution: int) -> list[dict]:
    """Getis-Ord Gi*-style hotspot detection aggregated by H3 cell.

    Args:
        records: crime dicts with ``h3_r{resolution}``, ``latitude``,
            ``longitude`` columns (any may be missing/None).
        resolution: H3 resolution (7, 8 or 9).

    Returns:
        ``[{h3, count, gi_score, significance, level, lat, lng}]`` sorted by
        count desc. ``gi_score`` is the local Gi* z-score; ``significance`` is
        in [0,1] (normal CDF of |z|); ``level`` is 'hot'/'cold'/'none'.
    """
    col = f"h3_r{resolution}" if resolution in (7, 8, 9) else "h3_r8"

    counts: dict = defaultdict(int)
    sample_ll: dict = {}
    for r in records:
        idx = r.get(col)
        if not idx:
            continue
        counts[idx] += 1
        if idx not in sample_ll:
            sample_ll[idx] = (r.get("latitude"), r.get("longitude"))

    if not counts:
        return []

    cells = list(counts.keys())
    vals = np.array([counts[c] for c in cells], dtype=float)
    n = len(cells)
    global_mean = float(vals.mean())
    # Global standard deviation of the attribute (population form).
    global_std = float(vals.std())
    if global_std == 0:
        global_std = 1.0

    out = []

    if h3 is not None and n > 1:
        # Gi* : local sum over the cell + its k-ring (k=1) neighbours, including
        # the focal cell (the 'star' in Gi*). Weights w_ij = 1 within disk.
        # Gi* = (sum_j w_ij x_j - Xbar * sum_j w_ij) /
        #       (S * sqrt[ (n * sum w_ij^2 - (sum w_ij)^2) / (n - 1) ])
        for i, c in enumerate(cells):
            try:
                disk = h3.grid_disk(c, 1)
            except Exception:
                disk = [c]
            local_sum = 0.0
            wsum = 0
            for nb in disk:
                wsum += 1
                local_sum += counts.get(nb, 0)
            # binary weights -> sum w^2 == wsum
            denom_inner = (n * wsum - wsum * wsum) / (n - 1)
            if denom_inner <= 1e-9 or wsum >= n:
                # Neighbourhood covers ~all cells: Gi* is undefined/unstable
                # (variance term collapses). Fall back to a simple z of the
                # local mean so the score stays bounded and meaningful.
                local_mean = local_sum / max(wsum, 1)
                z = (local_mean - global_mean) / global_std
            else:
                denom = global_std * math.sqrt(denom_inner)
                z = (local_sum - global_mean * wsum) / denom
            # Clamp to a sane, presentable range.
            z = float(max(-8.0, min(8.0, z)))
            lat, lng = _centroid(c, *sample_ll.get(c, (None, None)))
            level = "hot" if z >= 1.96 else ("cold" if z <= -1.96 else "none")
            out.append({
                "h3": c,
                "count": int(counts[c]),
                "gi_score": round(float(z), 3),
                "significance": round(_norm_sf(z), 3),
                "level": level,
                "lat": lat,
                "lng": lng,
            })
    else:
        # Fallback: global z-score (no spatial neighbourhood).
        for c in cells:
            z = (counts[c] - global_mean) / global_std
            lat, lng = _centroid(c, *sample_ll.get(c, (None, None)))
            level = "hot" if z >= 1.5 else ("cold" if z <= -1.0 else "none")
            out.append({
                "h3": c,
                "count": int(counts[c]),
                "gi_score": round(float(z), 3),
                "significance": round(_norm_sf(z), 3),
                "level": level,
                "lat": lat,
                "lng": lng,
            })

    out.sort(key=lambda x: -x["count"])
    return out


def _to_ordinal(iso: str):
    """Parse an ISO date prefix (YYYY-MM-DD) to a day ordinal, or None."""
    if not iso:
        return None
    try:
        y, m, d = (int(x) for x in str(iso)[:10].split("-")[:3])
        from datetime import date
        return date(y, m, d).toordinal()
    except Exception:
        return None


def emerging_hotspots(records: list[dict], resolution: int, period_days: int) -> list[dict]:
    """Emerging Hot Spot Analysis: recent window vs historical baseline.

    For each H3 cell we count incidents in the most recent ``period_days``
    window (``recent``) and compare to the average activity over equivalent
    prior windows (``baseline``, rate-normalised to the same window length).
    Each cell is classified:

        new          -- meaningful recent activity, ~no history
        intensifying -- recent clearly exceeds baseline
        diminishing  -- recent clearly below baseline
        persistent   -- stable presence across both
        sporadic     -- low/occasional recent activity
        none         -- excluded from output

    Returns ``[{h3, lat, lng, category, recent, baseline, change_pct}]``
    (excluding 'none'), robust to missing dates/cells.
    """
    col = f"h3_r{resolution}" if resolution in (7, 8, 9) else "h3_r8"
    period_days = max(1, int(period_days or 1))

    ords = []
    parsed = []  # (idx, ordinal, lat, lng)
    for r in records:
        idx = r.get(col)
        o = _to_ordinal(r.get("occurred_at"))
        if not idx or o is None:
            continue
        parsed.append((idx, o, r.get("latitude"), r.get("longitude")))
        ords.append(o)

    if not parsed:
        return []

    latest = max(ords)
    earliest = min(ords)
    cutoff = latest - period_days
    span = max(1, latest - earliest)
    # Number of equivalent prior windows available for baseline averaging.
    n_prior_windows = max(1.0, (cutoff - earliest) / period_days)

    recent: dict = defaultdict(int)
    historical: dict = defaultdict(int)
    centroid: dict = {}
    for idx, o, lat, lng in parsed:
        if idx not in centroid:
            centroid[idx] = (lat, lng)
        if o > cutoff:
            recent[idx] += 1
        else:
            historical[idx] += 1

    out = []
    for idx in set(recent) | set(historical):
        rec = recent.get(idx, 0)
        hist = historical.get(idx, 0)
        # Baseline expressed as expected count per recent-length window.
        baseline = hist / n_prior_windows
        if baseline > 0:
            change_pct = round(100.0 * (rec - baseline) / baseline, 1)
        else:
            change_pct = None

        if hist == 0 and rec >= 3:
            cat = "new"
        elif baseline > 0 and rec >= max(3, baseline * 1.3) and rec > baseline * 1.3:
            cat = "intensifying"
        elif baseline > 0 and rec <= baseline * 0.6:
            cat = "diminishing"
        elif rec > 0 and baseline > 0 and 0.6 < rec / baseline < 1.4:
            cat = "persistent"
        elif rec > 0:
            cat = "sporadic"
        else:
            cat = "none"

        if cat == "none":
            continue

        lat, lng = centroid.get(idx, (None, None))
        clat, clng = _centroid(idx, lat, lng)
        out.append({
            "h3": idx,
            "lat": clat,
            "lng": clng,
            "category": cat,
            "recent": int(rec),
            "baseline": round(float(baseline), 2),
            "change_pct": change_pct,
        })

    # Most interesting (largest absolute change / newest) first.
    order = {"new": 0, "intensifying": 1, "diminishing": 2, "persistent": 3, "sporadic": 4}
    out.sort(key=lambda x: (order.get(x["category"], 9), -x["recent"]))
    return out
