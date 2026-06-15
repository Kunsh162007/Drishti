"""Production entity resolution via Splink (probabilistic Fellegi–Sunter linkage).

Splink is imported lazily. When unavailable, it falls back to the demo's calibrated
rapidfuzz resolver so the endpoint always works. Mid-confidence matches go to a
human-review band — never auto-merged — preserving the no-fabricated-links rule.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _fallback(persons: list[dict], threshold: float) -> list[dict]:
    from demo.backend.analytics import entity_resolution as er  # shared pure logic
    return er.resolve_entities(persons, threshold)


def resolve(persons: list[dict], threshold: float = 0.9) -> list[dict]:
    """Return calibrated duplicate-identity pairs with decision bands.

    Tries Splink (DuckDB backend); on any failure, uses the calibrated fallback.
    """
    try:
        import pandas as pd
        from splink import DuckDBAPI, Linker, SettingsCreator, block_on
        import splink.comparison_library as cl

        df = pd.DataFrame(persons)
        if df.empty or "full_name" not in df.columns:
            return _fallback(persons, threshold)
        df = df.rename(columns={"person_id": "unique_id"})

        settings = SettingsCreator(
            link_type="dedupe_only",
            blocking_rules_to_generate_predictions=[block_on("normalized_name"), block_on("phone")],
            comparisons=[
                cl.JaroWinklerAtThresholds("full_name", [0.9, 0.7]),
                cl.ExactMatch("phone").configure(term_frequency_adjustments=True),
            ],
        )
        linker = Linker(df, settings, db_api=DuckDBAPI())
        linker.training.estimate_probability_two_random_records_match(
            [block_on("phone")], recall=0.7)
        linker.training.estimate_u_using_random_sampling(max_pairs=1e6)
        preds = linker.inference.predict(threshold_match_probability=max(0.5, threshold - 0.3))
        pdf = preds.as_pandas_dataframe()
        out = []
        for _, r in pdf.iterrows():
            score = float(r["match_probability"])
            decision = "auto" if score >= 0.97 else ("review" if score >= threshold else "reject")
            if decision == "reject":
                continue
            out.append({"a": r.get("full_name_l"), "b": r.get("full_name_r"),
                        "a_fir": r.get("fir_number_l"), "b_fir": r.get("fir_number_r"),
                        "score": round(score, 3),
                        "evidence": [f"Splink match probability {score:.3f}"],
                        "decision": decision})
        return sorted(out, key=lambda x: -x["score"])
    except Exception:
        return _fallback(persons, threshold)
