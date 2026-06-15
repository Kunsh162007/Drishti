"""Patrol / resource optimisation for DRISHTI -- PLACE-BASED only.

Allocates a fixed number of patrol units to the highest-risk H3 hexagons.
The risk per hex is a recency- and severity-weighted incident score (the same
explainable, place-based logic family as ``risk.py``); allocation is a greedy
assignment of one unit per top hex in descending risk order.

IMPORTANT (fairness): this module allocates patrols to *places*, never to
people. It produces no individual-level prediction or targeting. Every
assignment carries a plain-language ``rationale`` so the decision is auditable.

Pure function: list[dict] in -> JSON-serialisable dict out. Robust to missing
fields. Falls back gracefully if the ``h3`` library is unavailable.
"""
from __future__ import annotations

from collections import defaultdict

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


def optimize_patrol(records: list[dict], resolution: int, units: int) -> dict:
    """Greedily assign ``units`` patrols to the highest-risk hexes.

    Args:
        records: crime dicts with ``h3_r{resolution}``, ``occurred_at``,
            ``severity``, ``hour``, ``crime_type`` (any may be missing/None).
        resolution: H3 resolution (7, 8 or 9).
        units: number of patrol units to allocate (one per top hex).

    Returns:
        ``{assignments:[{h3, lat, lng, units, expected_share, top_type,
        rationale}], coverage_pct, summary}``. ``expected_share`` is the hex's
        share of total recency/severity-weighted incident load. Place-based:
        patrols are sent to locations, never to individuals.
    """
    col = f"h3_r{resolution}" if resolution in (7, 8, 9) else "h3_r8"
    units = max(0, int(units or 0))

    all_ords = [o for o in (_ordinal(r.get("occurred_at")) for r in records or []) if o is not None]
    latest = max(all_ords) if all_ords else None
    half_life = 180.0

    cells = defaultdict(lambda: {
        "w": 0.0, "n": 0, "night": 0, "sev_sum": 0.0, "sev_n": 0,
        "lat": None, "lng": None, "types": defaultdict(int),
    })

    for r in records or []:
        idx = r.get(col)
        if not idx:
            continue
        c = cells[idx]
        c["n"] += 1
        if c["lat"] is None:
            c["lat"], c["lng"] = r.get("latitude"), r.get("longitude")

        o = _ordinal(r.get("occurred_at"))
        if o is not None and latest is not None:
            age = max(0, latest - o)
            recency = 0.5 ** (age / half_life)
        else:
            recency = 0.5

        try:
            sv = float(r.get("severity")) if r.get("severity") is not None else 3.0
        except Exception:
            sv = 3.0
        # severity 1-5 scaled to ~0.4-1.0 multiplier so high-severity hexes weigh more
        sev_mult = 0.4 + 0.15 * max(0.0, min(4.0, sv - 1.0))
        c["w"] += recency * sev_mult
        c["sev_sum"] += sv
        c["sev_n"] += 1

        h = r.get("hour")
        try:
            h = int(h) if h is not None else None
        except Exception:
            h = None
        if h is not None and (h >= 20 or h <= 5):
            c["night"] += 1

        ct = r.get("crime_type")
        if ct:
            c["types"][ct] += 1

    if not cells:
        return {"assignments": [], "coverage_pct": 0.0,
                "summary": "No geocoded incidents available to plan patrols."}

    total_w = sum(c["w"] for c in cells.values()) or 1.0

    ranked = sorted(cells.items(), key=lambda kv: -kv[1]["w"])

    assignments = []
    covered_w = 0.0
    for idx, c in ranked[:units]:
        share = c["w"] / total_w
        covered_w += c["w"]
        lat, lng = _centroid(idx, c["lat"], c["lng"])
        top_type = (max(c["types"].items(), key=lambda kv: kv[1])[0]
                    if c["types"] else None)
        mean_sev = (c["sev_sum"] / c["sev_n"]) if c["sev_n"] else None
        night_share = c["night"] / c["n"] if c["n"] else 0.0

        bits = [f"{c['n']} recent incidents ({round(share * 100, 1)}% of weighted load)"]
        if top_type:
            bits.append(f"recurring {top_type}")
        if mean_sev is not None and mean_sev >= 3.5:
            bits.append(f"high severity ({mean_sev:.1f}/5)")
        if night_share > 0.4:
            bits.append(f"{round(night_share * 100)}% night-time")
        rationale = "; ".join(bits)

        assignments.append({
            "h3": idx,
            "lat": lat,
            "lng": lng,
            "units": 1,
            "expected_share": round(float(share), 4),
            "top_type": top_type,
            "rationale": rationale,
        })

    coverage_pct = round(100.0 * covered_w / total_w, 1)
    n_assigned = len(assignments)
    summary = (
        f"Allocated {n_assigned} patrol unit(s) to the top {n_assigned} hex(es), "
        f"covering ~{coverage_pct}% of the recency/severity-weighted incident load "
        f"across {len(cells)} active hex(es). Place-based allocation only."
    )
    if units > len(ranked):
        summary += f" Requested {units} units but only {len(ranked)} active hexes exist."

    return {
        "assignments": assignments,
        "coverage_pct": coverage_pct,
        "summary": summary,
    }
