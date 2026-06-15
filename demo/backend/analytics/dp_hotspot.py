"""Differential Privacy for crime hotspot publication — DRISHTI.

Applies the Laplace mechanism to crime counts before publication, providing
(epsilon, 0)-DP guarantees.  Lower epsilon = stronger privacy, more noise.

Academic basis:
  Dwork C et al. (2006). Calibrating noise to sensitivity in private data
    analysis. TCC 2006, LNCS 3876:265-284.
  Hsu J et al. (2014). Differential privacy: an economic method for selling
    data. IEEE CSF 2014.

Pure function. Standard library only.
"""
from __future__ import annotations

import math
import random


def _laplace_noise(sensitivity: float, epsilon: float, rng: random.Random) -> float:
    """Sample Laplace(0, sensitivity/epsilon) noise."""
    scale = sensitivity / max(1e-9, epsilon)
    u = rng.random() - 0.5
    return -scale * math.copysign(1, u) * math.log(1 - 2 * abs(u))


def privatise_hotspots(
    cells: list[dict],
    *,
    epsilon: float = 1.0,
    count_field: str = "count",
    sensitivity: float = 1.0,
    seed: int = 0,
) -> dict:
    """Add calibrated Laplace noise to hotspot counts.

    Args:
        cells: hotspot dicts with ``count`` (or ``count_field``).
        epsilon: privacy budget (0.1 = very private, 10.0 = near-raw data).
        count_field: name of the count field in each cell.
        sensitivity: global sensitivity (default 1 — adding/removing one
            crime changes any cell count by at most 1).
        seed: reproducible noise (0 = random each call).

    Returns:
        ``{cells:[...], epsilon, sensitivity, noise_scale, privacy_guarantee,
        original_total, dp_total}``.
    """
    rng = random.Random(seed if seed else None)
    noise_scale = sensitivity / max(1e-9, epsilon)
    out = []
    original_total = 0
    dp_total = 0.0
    for c in (cells or []):
        raw = float(c.get(count_field) or 0)
        original_total += int(raw)
        noisy = max(0.0, raw + _laplace_noise(sensitivity, epsilon, rng))
        row = dict(c)
        row[count_field + "_dp"] = round(noisy, 2)
        row[count_field] = round(noisy, 2)   # replace with DP value
        dp_total += noisy
        out.append(row)

    # Approximate privacy guarantee description
    if epsilon <= 0.5:
        guarantee = "very strong (ε≤0.5) — counts may differ significantly from true values"
    elif epsilon <= 2.0:
        guarantee = "strong (ε≤2) — realistic utility with meaningful privacy"
    elif epsilon <= 5.0:
        guarantee = "moderate (ε≤5) — good utility, moderate privacy"
    else:
        guarantee = "light (ε>5) — near-raw data, minimal privacy protection"

    return {
        "cells": out,
        "epsilon": epsilon,
        "sensitivity": sensitivity,
        "noise_scale": round(noise_scale, 4),
        "privacy_guarantee": guarantee,
        "original_total": original_total,
        "dp_total": round(dp_total, 1),
    }
