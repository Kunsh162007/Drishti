"""Case Correlation Engine for DRISHTI.

Groups FIRs into clusters of potentially related crimes using a multi-signal
similarity score: spatial proximity, temporal proximity, crime type, weapon,
and modus-operandi keyword overlap.  Uses union-find for O(N α(N)) clustering.

Academic basis:
  Haarr RN (1997). Patterns in routine activities and crime.
  Eck J & Weisburd D (1995). Crime places in crime theory. Crime and Place.
  Chainey S & Ratcliffe J (2005). GIS and Crime Mapping. Wiley.

Pure function. Standard library only.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict


# ── Helpers ──────────────────────────────────────────────────────────────────

def _haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _date_to_int(s: str) -> int:
    """'YYYY-MM-DD ...' → integer days since epoch (approximate)."""
    try:
        parts = re.split(r"[-T/ ]", str(s or ""))
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return y * 365 + m * 30 + d
    except Exception:
        return 0


def _mo_tokens(text: str) -> set[str]:
    if not text:
        return set()
    return set(re.findall(r"[a-z]{4,}", text.lower()))


# ── Union-Find ────────────────────────────────────────────────────────────────

class _UF:
    def __init__(self, n):
        self.p = list(range(n))
        self.rank = [0] * n

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.p[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(a: dict, b: dict) -> float:
    s = 0.0
    # Spatial
    lat_a, lng_a = a.get("latitude"), a.get("longitude")
    lat_b, lng_b = b.get("latitude"), b.get("longitude")
    if lat_a and lat_b and lng_a and lng_b:
        try:
            km = _haversine_km(float(lat_a), float(lng_a), float(lat_b), float(lng_b))
            if km <= 1.0:
                s += 3.0
            elif km <= 5.0:
                s += 1.5
            elif km <= 15.0:
                s += 0.5
        except Exception:
            pass
    # Same H3 cell (resolution 8 ≈ 0.75 km)
    if a.get("h3_r8") and a.get("h3_r8") == b.get("h3_r8"):
        s += 2.0
    elif a.get("h3_r7") and a.get("h3_r7") == b.get("h3_r7"):
        s += 0.5
    # Temporal
    da, db = _date_to_int(a.get("occurred_at")), _date_to_int(b.get("occurred_at"))
    if da and db:
        diff = abs(da - db)
        if diff <= 7:
            s += 2.5
        elif diff <= 30:
            s += 1.0
        elif diff <= 90:
            s += 0.3
    # Crime type
    if a.get("crime_type") and a.get("crime_type") == b.get("crime_type"):
        s += 2.0
    elif a.get("crime_category") and a.get("crime_category") == b.get("crime_category"):
        s += 0.5
    # Weapon
    wa, wb = a.get("weapon_used"), b.get("weapon_used")
    if wa and wb and wa.strip().lower() == wb.strip().lower():
        s += 1.5
    # MO keyword Jaccard
    ta, tb = _mo_tokens(a.get("modus_operandi") or ""), _mo_tokens(b.get("modus_operandi") or "")
    if ta and tb:
        inter = len(ta & tb)
        union = len(ta | tb)
        if union:
            s += (inter / union) * 4.0
    return s


# ── Public API ────────────────────────────────────────────────────────────────

def correlate_cases(
    crimes: list[dict],
    persons: list[dict] | None = None,
    vehicles: list[dict] | None = None,
    *,
    threshold: float = 4.0,
    max_clusters: int = 30,
    min_cluster_size: int = 2,
    max_pairs: int = 8000,
) -> dict:
    """Cluster FIRs into correlated groups.

    Args:
        crimes: list of crime dicts (from Crime.as_dict()).
        persons: optional person records for cross-FIR person links.
        vehicles: optional vehicle records.
        threshold: minimum similarity score to link two FIRs.
        max_clusters: cap on returned clusters (largest first).
        min_cluster_size: skip singletons and pairs below this.
        max_pairs: cap on pairs examined (performance guard).

    Returns:
        ``{clusters:[{id, firs:[{...}], signals:[str], size, score}],
           total_crimes, total_linked, method, threshold}``.
    """
    n = len(crimes)
    if n < 2:
        return {"clusters": [], "total_crimes": n, "total_linked": 0,
                "method": "multi-signal", "threshold": threshold}

    uf = _UF(n)
    pair_scores: dict[tuple[int, int], float] = {}

    # ── Content-similarity pairs ──────────────────────────────────────────────
    examined = 0
    for i in range(n):
        for j in range(i + 1, n):
            if examined >= max_pairs:
                break
            sc = _score(crimes[i], crimes[j])
            if sc >= threshold:
                uf.union(i, j)
                pair_scores[(i, j)] = sc
            examined += 1
        if examined >= max_pairs:
            break

    # ── Person-link pairs (same person appears in both FIRs) ─────────────────
    if persons:
        fir_to_idx = {c["fir_number"]: idx for idx, c in enumerate(crimes) if c.get("fir_number")}
        tid_to_firs: dict[str, list[str]] = defaultdict(list)
        for p in persons:
            tid = p.get("true_identity_id") or p.get("person_id", "")
            fir = p.get("fir_number", "")
            if tid and fir:
                tid_to_firs[tid].append(fir)
        for tid, firs in tid_to_firs.items():
            idxs = [fir_to_idx[f] for f in firs if f in fir_to_idx]
            for ii in range(len(idxs)):
                for jj in range(ii + 1, len(idxs)):
                    uf.union(idxs[ii], idxs[jj])
                    pair_scores.setdefault((min(idxs[ii], idxs[jj]), max(idxs[ii], idxs[jj])), 2.0)

    # ── Vehicle-link pairs ────────────────────────────────────────────────────
    if vehicles:
        fir_to_idx = {c["fir_number"]: idx for idx, c in enumerate(crimes) if c.get("fir_number")}
        reg_to_firs: dict[str, list[str]] = defaultdict(list)
        for v in vehicles:
            reg = (v.get("reg_number") or "").strip().upper()
            fir = v.get("fir_number", "")
            if reg and fir:
                reg_to_firs[reg].append(fir)
        for reg, firs in reg_to_firs.items():
            idxs = [fir_to_idx[f] for f in set(firs) if f in fir_to_idx]
            for ii in range(len(idxs)):
                for jj in range(ii + 1, len(idxs)):
                    uf.union(idxs[ii], idxs[jj])
                    pair_scores.setdefault((min(idxs[ii], idxs[jj]), max(idxs[ii], idxs[jj])), 2.5)

    # ── Collect clusters ──────────────────────────────────────────────────────
    root_to_idxs: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        root_to_idxs[uf.find(i)].append(i)

    clusters = []
    for root, idxs in root_to_idxs.items():
        if len(idxs) < min_cluster_size:
            continue
        firs_in = [crimes[i] for i in idxs]
        # Collect signals present
        signals: list[str] = []
        types = {c.get("crime_type") for c in firs_in if c.get("crime_type")}
        weapons = {c.get("weapon_used") for c in firs_in if c.get("weapon_used")}
        districts = {c.get("district") for c in firs_in if c.get("district")}
        if len(types) == 1:
            signals.append(f"Same type: {next(iter(types))}")
        if weapons:
            signals.append(f"Weapon: {', '.join(list(weapons)[:2])}")
        if len(districts) == 1:
            signals.append(f"Same district: {next(iter(districts))}")
        else:
            signals.append(f"Cross-district ({len(districts)} districts)")
        # Cluster score = mean pairwise score among linked pairs in this cluster
        idx_set = set(idxs)
        sc_vals = [v for (i, j), v in pair_scores.items() if i in idx_set and j in idx_set]
        cluster_score = round(sum(sc_vals) / max(1, len(sc_vals)), 2) if sc_vals else threshold
        clusters.append({
            "id": f"CLU-{root:04d}",
            "firs": sorted(firs_in, key=lambda c: c.get("occurred_at") or ""),
            "size": len(idxs),
            "score": cluster_score,
            "signals": signals,
            "crime_types": sorted(types),
            "districts": sorted(districts),
        })

    clusters.sort(key=lambda c: (-c["size"], -c["score"]))
    clusters = clusters[:max_clusters]
    total_linked = sum(c["size"] for c in clusters)

    return {
        "clusters": clusters,
        "total_crimes": n,
        "total_linked": total_linked,
        "method": "multi-signal (spatial + temporal + MO + type + weapon + person + vehicle)",
        "threshold": threshold,
    }
