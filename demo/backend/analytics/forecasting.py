"""Crime-count forecasting for DRISHTI — Holt's double-exponential smoothing.

Produces point forecasts with 95%-style confidence intervals derived from
in-sample residuals.  Also detects near-repeat spikes using a simple Knox-
inspired temporal buffer.

Academic basis:
  Holt CC (1957). Forecasting seasonals and trends by exponentially weighted
    averages. ONR Memorandum 52.
  Johnson SD (2008). Repeat burglary victimisation: a tale of two theories.
    Journal of Experimental Criminology 4:215-240.
  Chainey & Ratcliffe (2005). GIS and Crime Mapping. Wiley.

Pure function: list[dict] in -> JSON-serialisable dict out. Standard library only.
"""
from __future__ import annotations

import math
from collections import Counter


def _holt(series: list[float], alpha: float = 0.35, beta: float = 0.12) -> tuple[list[float], float, float]:
    """Holt double exponential smoothing.

    Returns (fitted_values, last_level, last_trend).
    """
    if not series:
        return [], 0.0, 0.0
    if len(series) == 1:
        return [float(series[0])], float(series[0]), 0.0

    level = float(series[0])
    trend = float(series[1]) - float(series[0])
    fitted = []
    for obs in series:
        obs = float(obs)
        prev_l, prev_t = level, trend
        level = alpha * obs + (1 - alpha) * (prev_l + prev_t)
        trend = beta * (level - prev_l) + (1 - beta) * prev_t
        fitted.append(prev_l + prev_t)
    return fitted, level, trend


def _next_period(period: str, steps: int = 1) -> str:
    year, month = int(period[:4]), int(period[5:7])
    for _ in range(steps):
        month += 1
        if month > 12:
            month = 1
            year += 1
    return f"{year:04d}-{month:02d}"


def forecast_crimes(
    monthly_counts: list[dict],
    *,
    horizon: int = 3,
    alpha: float = 0.35,
    beta: float = 0.12,
    min_history: int = 3,
) -> dict:
    """Forecast crime counts for the next ``horizon`` months.

    Args:
        monthly_counts: ``[{period: "YYYY-MM", count: int}]`` sorted asc.
        horizon: months to forecast ahead (1–12).
        alpha: Holt level smoothing parameter.
        beta: Holt trend smoothing parameter.
        min_history: minimum historical points required; returns empty
            forecast if fewer points are available.

    Returns:
        ``{history, forecast:[{period,count,lo,hi}], trend, model, rmse,
        peak_period, peak_count}``.
    """
    pts = sorted(
        [p for p in (monthly_counts or []) if p.get("period") and p.get("count") is not None],
        key=lambda x: x["period"],
    )
    if len(pts) < min_history:
        return {
            "history": [{"period": p["period"], "count": p["count"]} for p in pts],
            "forecast": [],
            "trend": "stable",
            "model": "holt",
            "rmse": 0,
            "peak_period": None,
            "peak_count": 0,
        }

    series = [float(p["count"]) for p in pts]
    fitted, level, trend = _holt(series, alpha, beta)

    # RMSE from in-sample residuals (skip first point — unfitted)
    res = [abs(series[i] - fitted[i]) for i in range(1, len(series))]
    rmse = math.sqrt(sum(r ** 2 for r in res) / len(res)) if res else 0.0

    last_period = pts[-1]["period"]
    horizon = max(1, min(12, int(horizon)))

    forecast = []
    for h in range(1, horizon + 1):
        period = _next_period(last_period, h)
        fc = max(0.0, level + h * trend)
        # 95% interval widens with step: ~1.96 * RMSE * sqrt(h)
        margin = 1.96 * rmse * math.sqrt(h)
        forecast.append({
            "period": period,
            "count": round(fc, 1),
            "lo": round(max(0.0, fc - margin), 1),
            "hi": round(fc + margin, 1),
        })

    # Trend classification (last 3 vs prior 3 months)
    if len(series) >= 6:
        recent = sum(series[-3:]) / 3
        prior = sum(series[-6:-3]) / 3
        if prior > 0:
            pct = (recent - prior) / prior
            if pct > 0.05:
                trend_dir = "rising"
            elif pct < -0.05:
                trend_dir = "falling"
            else:
                trend_dir = "stable"
        else:
            trend_dir = "rising" if recent > 0 else "stable"
    else:
        trend_dir = "rising" if trend > 0.5 else ("falling" if trend < -0.5 else "stable")

    peak = max(pts, key=lambda p: p["count"])

    return {
        "history": [{"period": p["period"], "count": p["count"]} for p in pts],
        "forecast": forecast,
        "trend": trend_dir,
        "model": f"Holt ETS(α={alpha}, β={beta})",
        "rmse": round(rmse, 2),
        "peak_period": peak["period"],
        "peak_count": peak["count"],
    }


def near_repeat_risk(records: list[dict], *, days_window: int = 14, radius_km: float = 0.5) -> list[dict]:
    """Identify crime locations with elevated near-repeat risk.

    After a crime at location L, there is a heightened risk of repeat
    victimisation within `radius_km` for `days_window` days (Johnson 2008).

    Args:
        records: crime dicts with ``latitude``, ``longitude``, ``occurred_at``.
        days_window: temporal buffer in days.
        radius_km: spatial buffer radius.

    Returns:
        ``[{lat, lng, fir_number, trigger_fir, days_since, distance_km,
        crime_type}]`` — locations currently within the risk window of a
        prior crime.
    """
    import datetime

    valid = []
    for r in records or []:
        try:
            lat = float(r.get("latitude") or 0)
            lng = float(r.get("longitude") or 0)
            if lat == 0 and lng == 0:
                continue
            occ = str(r.get("occurred_at") or "")[:10]
            if not occ or len(occ) < 10:
                continue
            d = datetime.date(*map(int, occ.split("-")))
            valid.append((d, lat, lng, r.get("fir_number", ""), r.get("crime_type", "")))
        except Exception:
            continue

    if not valid:
        return []

    valid.sort(key=lambda x: x[0])
    today = valid[-1][0]  # treat latest crime date as "now"

    def haversine_km(lat1, lon1, lat2, lon2):
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return R * 2 * math.asin(math.sqrt(max(0.0, a)))

    results = []
    seen = set()
    for i in range(len(valid) - 1, -1, -1):
        td, tlat, tlng, tfir, ttype = valid[i]
        days_since = (today - td).days
        if days_since > days_window:
            break
        for j in range(i - 1, -1, -1):
            bd, blat, blng, bfir, btype = valid[j]
            dist = haversine_km(tlat, tlng, blat, blng)
            if dist <= radius_km:
                key = (tfir, bfir)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "lat": round(tlat, 5),
                        "lng": round(tlng, 5),
                        "fir_number": tfir,
                        "trigger_fir": bfir,
                        "days_since": days_since,
                        "distance_km": round(dist, 3),
                        "crime_type": ttype,
                    })
    return results[:200]
