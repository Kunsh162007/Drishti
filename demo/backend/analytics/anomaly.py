"""Crime-record anomaly detection for DRISHTI.

Uses scikit-learn's **Isolation Forest** (Liu, Ting & Zhou 2008), an
ensemble of random isolation trees that scores how easily a record is
isolated -- outliers are isolated with fewer splits. We engineer numeric
features (temporal, severity, monetary, party counts, frequency-encoded
crime type / district) and surface human-readable ``reasons`` derived from
the features that deviate most from the typical record.

Pure function: list[dict] in -> list[dict] out. Robust to missing fields.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def _num(v, default=np.nan):
    try:
        if v is None:
            return default
        f = float(v)
        if math.isnan(f):
            return default
        return f
    except Exception:
        return default


def detect_anomalies(records: list[dict], limit: int) -> list[dict]:
    """Detect the most anomalous crime records via Isolation Forest.

    Args:
        records: crime dicts (canonical columns; any may be missing/None).
        limit: maximum number of anomalies to return.

    Returns:
        ``[{fir_number, score, reasons[], ...all crime fields...}]`` sorted by
        score desc. ``score`` is in [0,1] (1 = most anomalous). ``reasons``
        are plain-language explanations from the most deviant features.
    """
    if not records:
        return []
    limit = max(1, int(limit or 1))

    df = pd.DataFrame(records)
    n = len(df)
    if n < 4:
        # Too few rows for a meaningful forest; return them flagged mildly.
        out = []
        for r in records[:limit]:
            out.append({"fir_number": r.get("fir_number"), "score": 0.0,
                        "reasons": ["insufficient data for anomaly model"], **r})
        return out

    # ---- feature engineering ---------------------------------------------
    hour = df.get("hour", pd.Series([np.nan] * n)).map(_num)
    dow = df.get("day_of_week", pd.Series([np.nan] * n)).map(_num)
    severity = df.get("severity", pd.Series([np.nan] * n)).map(_num)
    victims = df.get("victim_count", pd.Series([np.nan] * n)).map(_num)
    accused = df.get("accused_count", pd.Series([np.nan] * n)).map(_num)
    prop = df.get("property_value_inr", pd.Series([np.nan] * n)).map(_num)
    log_prop = np.log1p(prop.fillna(0.0).clip(lower=0))

    # Frequency encoding for high-cardinality categoricals.
    def freq_encode(colname):
        s = df.get(colname, pd.Series([None] * n)).astype("object")
        counts = s.value_counts(dropna=True)
        return s.map(lambda v: counts.get(v, 0) / n if v is not None else 0.0).astype(float)

    type_freq = freq_encode("crime_type")
    dist_freq = freq_encode("district")

    feat = pd.DataFrame({
        "hour": hour.fillna(hour.median() if hour.notna().any() else 12.0),
        "dow": dow.fillna(dow.median() if dow.notna().any() else 3.0),
        "severity": severity.fillna(severity.median() if severity.notna().any() else 3.0),
        "victims": victims.fillna(0.0),
        "accused": accused.fillna(0.0),
        "log_prop": log_prop,
        "type_freq": type_freq,
        "dist_freq": dist_freq,
    })

    X = feat.to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    model = IsolationForest(
        n_estimators=200, contamination="auto", random_state=42, n_jobs=-1,
    )
    model.fit(X)
    # decision_function: higher = more normal. Invert + min-max to [0,1].
    raw = -model.decision_function(X)
    lo, hi = float(raw.min()), float(raw.max())
    if hi - lo < 1e-12:
        scores = np.zeros(n)
    else:
        scores = (raw - lo) / (hi - lo)

    # ---- reason generation: which features are most deviant -------------
    mu = feat.mean(axis=0)
    sd = feat.std(axis=0).replace(0, 1.0)
    zmat = (feat - mu) / sd

    def reasons_for(i):
        z = zmat.iloc[i]
        rs = []
        if z["log_prop"] > 2.0:
            rs.append("property value far above typical")
        elif z["log_prop"] < -2.0 and feat.iloc[i]["log_prop"] > 0:
            rs.append("unusually low reported property value")
        h = feat.iloc[i]["hour"]
        if abs(z["hour"]) > 1.8 or (1 <= h <= 4):
            rs.append("unusual hour of occurrence")
        if z["severity"] > 1.8:
            rs.append("severity higher than typical")
        if z["victims"] > 2.0:
            rs.append("unusually high victim count")
        if z["accused"] > 2.0:
            rs.append("unusually high accused count")
        if z["type_freq"] < -1.0:
            rs.append("rare crime type for this dataset")
        if z["dist_freq"] < -1.0:
            rs.append("atypical for this district")
        if not rs:
            # Generic fallback: name the single most deviant feature.
            label = {
                "hour": "unusual hour", "dow": "unusual day of week",
                "severity": "atypical severity", "victims": "atypical victim count",
                "accused": "atypical accused count", "log_prop": "atypical property value",
                "type_freq": "uncommon crime type", "dist_freq": "uncommon district",
            }
            top = z.abs().idxmax()
            rs.append(label.get(top, "statistically unusual record"))
        return rs

    idx_sorted = np.argsort(-scores)[:limit]
    out = []
    for i in idx_sorted:
        rec = records[int(i)]
        out.append({
            "fir_number": rec.get("fir_number"),
            "score": round(float(scores[i]), 3),
            "reasons": reasons_for(int(i)),
            **rec,
        })
    return out
