"""Geographic Profiling — Rossmo's Criminal Geographic Targeting (CGT).

Generates a probability surface over a geographic area from linked crime
locations, identifying anchor-point candidates (home, workplace, or habitual
activity nodes) via a distance-decay / buffer-zone model.

Academic basis:
  Rossmo DK (1999). Geographic Profiling. CRC Press.
  Levine N (2013). CrimeStat III.  NIJ.
  Chainey S & Ratcliffe J (2005). GIS and Crime Mapping. Wiley.

Pure function: list[dict] in -> JSON-serialisable dict out. No dependencies
beyond the Python standard library.
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0.0, a)))


def _deduplicate(pts: list[tuple[float, float]], min_sep_km: float = 0.1) -> list[tuple[float, float]]:
    unique: list[tuple[float, float]] = []
    for p in pts:
        if not any(_haversine_km(p[0], p[1], q[0], q[1]) < min_sep_km for q in unique):
            unique.append(p)
    return unique


# ---------------------------------------------------------------------------
# Rossmo CGT
# ---------------------------------------------------------------------------

def rossmo_surface(
    crime_locs: list[dict],
    *,
    grid_steps: int = 60,
    buffer_km: float = 1.5,
    f: float = 1.2,
    g: float = 1.2,
    lat_min: float = 11.5,
    lat_max: float = 18.6,
    lng_min: float = 74.0,
    lng_max: float = 78.6,
    top_n: int = 1400,
) -> dict:
    """Compute Rossmo's CGT probability grid over a bounding box.

    The formula assigns each grid point a score proportional to the
    likelihood of being an offender anchor point given the observed crime
    locations:

        score(g) = sum_i { phi_i / d_i^f  +  (1 - phi_i) * d_i^g / B^(f+g) }

    where phi_i = 1 if d_i > B (outside buffer), else 0; B = buffer_km.

    Args:
        crime_locs: ``[{lat, lng, ...}]`` — geocoded crime locations.
        grid_steps: resolution in each dimension (higher = finer grid).
        buffer_km: minimum expected distance from anchor to crime scene.
        f: distance-decay exponent outside buffer (typ. 1.2).
        g: distance-decay exponent inside buffer (typ. 1.2).
        lat_min, lat_max, lng_min, lng_max: bounding box (default = Karnataka).
        top_n: max grid points to return (highest probability first).

    Returns:
        ``{points:[{lat,lng,score}], anchor:{lat,lng}, total_crimes,
        unique_locs, params}``.
    """
    def _ll(c):
        # Accept both {lat,lng} and DB-native {latitude,longitude} keys.
        lat = c.get("lat", c.get("latitude"))
        lng = c.get("lng", c.get("longitude"))
        return lat, lng

    raw = [(float(lat), float(lng))
           for c in (crime_locs or [])
           for lat, lng in [_ll(c)]
           if lat is not None and lng is not None]

    if not raw:
        return {"points": [], "anchor": None, "total_crimes": 0,
                "unique_locs": 0, "params": {}}

    pts = _deduplicate(raw)

    if len(pts) < 2:
        lat0, lng0 = pts[0] if pts else raw[0]
        return {
            "points": [{"lat": round(lat0, 5), "lng": round(lng0, 5), "score": 1.0}],
            "anchor": {"lat": round(lat0, 5), "lng": round(lng0, 5)},
            "total_crimes": len(raw),
            "unique_locs": len(pts),
            "params": {"buffer_km": buffer_km, "f": f, "g": g},
        }

    lat_step = (lat_max - lat_min) / max(1, grid_steps)
    lng_step = (lng_max - lng_min) / max(1, grid_steps)
    B_fg = buffer_km ** (f + g)

    cells: list[tuple[float, float, float]] = []
    for i in range(grid_steps + 1):
        glat = lat_min + i * lat_step
        for j in range(grid_steps + 1):
            glng = lng_min + j * lng_step
            score = 0.0
            for clat, clng in pts:
                d = max(0.05, _haversine_km(glat, glng, clat, clng))
                if d > buffer_km:
                    score += 1.0 / (d ** f)
                else:
                    score += (d ** g) / B_fg
            cells.append((glat, glng, score))

    max_s = max(c[2] for c in cells) or 1.0
    norm = sorted(
        [(lat, lng, s / max_s) for lat, lng, s in cells],
        key=lambda x: -x[2],
    )

    anchor_lat, anchor_lng, _ = norm[0]
    return {
        "points": [
            {"lat": round(lat, 5), "lng": round(lng, 5), "score": round(s, 4)}
            for lat, lng, s in norm[:top_n]
        ],
        "anchor": {"lat": round(anchor_lat, 5), "lng": round(anchor_lng, 5)},
        "total_crimes": len(raw),
        "unique_locs": len(pts),
        "params": {"buffer_km": buffer_km, "f": f, "g": g, "grid_steps": grid_steps},
    }
