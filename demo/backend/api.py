"""DRISHTI demo API. All routes under /api. DB I/O lives here; analytics are pure functions.

Analytics modules are imported defensively: if a module is missing or errors, the endpoint
degrades to a simple built-in fallback so the app always boots and never crashes a request.
"""
import functools
import io
import json
import logging
import math
import statistics
from collections import Counter, defaultdict

import pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException

logger = logging.getLogger(__name__)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from . import config, assistant, audit
from .db import get_session, engine
from .models import Crime, Person, Vehicle, CDR, Account, Transaction, MissingPerson, AuditLog

router = APIRouter(prefix="/api")

# ---- demo auth (cosmetic gate; endpoints stay open, token is not enforced) -------------------
DEMO_USERS = {"officer": "drishti", "analyst": "drishti", "admin": "drishti"}


@router.post("/auth/login")
def auth_login(form: OAuth2PasswordRequestForm = Depends()):
    if DEMO_USERS.get(form.username) == form.password:
        return {"access_token": f"demo-{form.username}", "token_type": "bearer",
                "role": "analyst", "username": form.username}
    raise HTTPException(status_code=401, detail="Invalid demo credentials. Try officer / drishti")


@router.get("/auth/me")
def auth_me():
    return {"username": "officer", "role": "analyst", "mode": "demo"}

# ---- optional analytics (built by the analytics agent) -------------------------------------
try:
    from .analytics import hotspots as A_hotspots
except Exception:
    A_hotspots = None
try:
    from .analytics import anomaly as A_anomaly
except Exception:
    A_anomaly = None
try:
    from .analytics import entity_resolution as A_er
except Exception:
    A_er = None
try:
    from .analytics import mo_linkage as A_mo
except Exception:
    A_mo = None
try:
    from .analytics import risk as A_risk
except Exception:
    A_risk = None
try:
    from .analytics import communities as A_comm
except Exception:
    A_comm = None
try:
    from .analytics import nlp_extract as A_nlp
except Exception:
    A_nlp = None
try:
    from .analytics import cdr as A_cdr
except Exception:
    A_cdr = None
try:
    from .analytics import cyber as A_cyber
except Exception:
    A_cyber = None
try:
    from .analytics import patrol as A_patrol
except Exception:
    A_patrol = None
try:
    from .analytics import oversight as A_oversight
except Exception:
    A_oversight = None
try:
    from .analytics import briefing as A_briefing
except Exception:
    A_briefing = None

try:
    import h3
except Exception:
    h3 = None


# ---- helpers --------------------------------------------------------------------------------
def _filtered(db: Session, district=None, crime_type=None, category=None,
              date_from=None, date_to=None, q=None):
    query = db.query(Crime)
    if district:
        query = query.filter(Crime.district == district)
    if crime_type:
        query = query.filter(Crime.crime_type == crime_type)
    if category:
        query = query.filter(Crime.crime_category == category)
    if date_from:
        query = query.filter(Crime.occurred_at >= date_from)
    if date_to:
        query = query.filter(Crime.occurred_at <= date_to + "T23:59:59")
    if q:
        like = f"%{q}%"
        query = query.filter((Crime.modus_operandi.like(like)) | (Crime.description.like(like))
                             | (Crime.fir_number.like(like)) | (Crime.police_station.like(like)))
    return query


def _dicts(rows):
    return [r.as_dict() for r in rows]


# ---- Response cache -------------------------------------------------------------------------
# The demo dataset is static/read-only, so caching heavy analytics responses is
# safe and turns repeat/concurrent visits into instant cache hits — critical on
# the single 512MB free-tier AppSail instance, where recomputing over 25k rows
# concurrently otherwise crashes it. Ingest clears the cache (see /ingest).
import time as _time
_RESP_CACHE: dict = {}
_CACHE_MAX = 128


def _cache_clear():
    _RESP_CACHE.clear()


def cached(ttl: int = 600):
    """Cache a GET endpoint's return by its kwargs (excluding the db session)."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = (fn.__name__,) + tuple(sorted(
                (k, v) for k, v in kwargs.items() if k != "db" and not isinstance(v, Session)))
            hit = _RESP_CACHE.get(key)
            now = _time.time()
            if hit and now - hit[0] < ttl:
                return hit[1]
            val = fn(*args, **kwargs)
            if len(_RESP_CACHE) >= _CACHE_MAX:
                _RESP_CACHE.pop(next(iter(_RESP_CACHE)))
            _RESP_CACHE[key] = (now, val)
            return val
        return wrapper
    return deco


def _h3_centroid(idx):
    if h3 and idx:
        try:
            lat, lng = h3.cell_to_latlng(idx)
            return lat, lng
        except Exception:
            try:
                lat, lng = h3.h3_to_geo(idx)  # v3 fallback
                return lat, lng
            except Exception:
                return None, None
    return None, None


def _enrich_cells(cells, rows, resolution):
    """Attach a human-readable location (majority district + station) to each hex cell."""
    col = f"h3_r{resolution}" if resolution in (7, 8, 9) else "h3_r8"
    by_dist = defaultdict(Counter)
    by_station = defaultdict(Counter)
    for r in rows:
        hx = r.get(col)
        if hx and r.get("district"):
            by_dist[hx][r["district"]] += 1
            if r.get("police_station"):
                by_station[hx][r["police_station"]] += 1
    for c in cells:
        hx = c.get("h3")
        if hx and by_dist.get(hx):
            dist = by_dist[hx].most_common(1)[0][0]
            station = by_station[hx].most_common(1)[0][0] if by_station.get(hx) else None
            c["district"] = dist
            c["station"] = station
            c["label"] = f"{station}, {dist}" if station else dist
        else:
            c.setdefault("district", None)
            c.setdefault("station", None)
            c.setdefault("label", None)
    return cells


# ---- meta / health --------------------------------------------------------------------------
@router.get("/health")
def health(db: Session = Depends(get_session)):
    return {"status": "ok", "mode": config.MODE, "db": config.DATABASE_URL.split("://")[0],
            "records": db.query(func.count(Crime.id)).scalar() or 0}


@router.get("/test")
def api_test(db: Session = Depends(get_session)):
    """Diagnostic endpoint — hit /api/test in browser to verify each subsystem."""
    import traceback, sys, platform
    results = {}
    try:
        results["crimes"] = db.query(func.count(Crime.id)).scalar()
        results["persons"] = db.query(func.count(Person.id)).scalar()
        results["transactions"] = db.query(func.count(Transaction.id)).scalar()
        results["accounts"] = db.query(func.count(Account.id)).scalar()
        results["db_ok"] = True
    except Exception as e:
        results["db_ok"] = False
        results["db_error"] = traceback.format_exc()
    try:
        suresh = db.query(Person).filter(Person.full_name.ilike("%Suresh%")).limit(3).all()
        results["suresh_count"] = len(suresh)
        results["suresh_names"] = [p.full_name for p in suresh]
    except Exception as e:
        results["suresh_error"] = str(e)
    try:
        cyber_crimes = db.query(func.count(Crime.id)).filter(Crime.crime_category == "Cybercrime").scalar()
        results["cyber_crimes"] = cyber_crimes
    except Exception as e:
        results["cyber_error"] = str(e)
    results["python"] = sys.version
    results["platform"] = platform.platform()
    results["analytics"] = {
        "cyber": A_cyber is not None,
        "hotspots": A_hotspots is not None,
        "cdr": A_cdr is not None,
    }
    return results


@router.get("/meta")
def meta(db: Session = Depends(get_session)):
    districts = [d[0] for d in db.query(Crime.district).distinct().order_by(Crime.district)]
    types = [t[0] for t in db.query(Crime.crime_type).distinct().order_by(Crime.crime_type)]
    cats = [c[0] for c in db.query(Crime.crime_category).distinct().order_by(Crime.crime_category)]
    dmin = db.query(func.min(Crime.occurred_at)).scalar()
    dmax = db.query(func.max(Crime.occurred_at)).scalar()
    return {
        "districts": districts, "crime_types": types, "categories": cats,
        "date_range": {"min": (dmin or "")[:10], "max": (dmax or "")[:10]},
        "totals": {
            "crimes": db.query(func.count(Crime.id)).scalar() or 0,
            "persons": db.query(func.count(Person.id)).scalar() or 0,
            "vehicles": db.query(func.count(Vehicle.id)).scalar() or 0,
        },
    }


# ---- crimes / stats -------------------------------------------------------------------------
@router.get("/crimes")
def crimes(db: Session = Depends(get_session), district=None, crime_type=None, category=None,
           date_from=None, date_to=None, q=None, h3=None, limit: int = 500, offset: int = 0):
    base = _filtered(db, district, crime_type, category, date_from, date_to, q)
    if h3:
        base = base.filter((Crime.h3_r7 == h3) | (Crime.h3_r8 == h3) | (Crime.h3_r9 == h3))
    total = base.count()
    rows = base.order_by(Crime.occurred_at.desc()).offset(offset).limit(min(limit, 5000)).all()
    return {"total": total, "items": _dicts(rows)}


@router.get("/stats")
@cached(600)
def stats(db: Session = Depends(get_session), district=None, date_from=None, date_to=None):
    # SQL GROUP BY aggregation in the DB — avoids loading 25k rows into Python
    # (which was ~25s and memory-spiked the free-tier instance into crashing).
    base = _filtered(db, district=district, date_from=date_from, date_to=date_to)

    def grouped(col):
        return dict(base.with_entities(col, func.count(Crime.id)).group_by(col).all())

    by_cat = Counter(grouped(Crime.crime_category))
    by_dist = Counter(grouped(Crime.district))
    by_status = Counter(grouped(Crime.status))
    by_hour = [0] * 24
    for h, c in grouped(Crime.hour).items():
        if h is not None and 0 <= int(h) < 24:
            by_hour[int(h)] += c
    month_col = func.substr(Crime.occurred_at, 1, 7)
    by_month = {k: v for k, v in
                base.with_entities(month_col, func.count(Crime.id)).group_by(month_col).all() if k}
    solved = sum(by_status.get(s, 0) for s in ("ChargeSheeted", "Closed"))
    total = sum(by_cat.values())
    return {
        "kpis": {
            "total_crimes": total,
            "open_cases": by_status.get("Open", 0) + by_status.get("UnderInvestigation", 0),
            "solved_rate": round(100 * solved / total, 1) if total else 0,
            "districts_affected": len(by_dist),
            "violent_share": round(100 * by_cat.get("Violent", 0) / total, 1) if total else 0,
            "cyber_share": round(100 * by_cat.get("Cybercrime", 0) / total, 1) if total else 0,
        },
        "by_category": [{"name": k, "value": v} for k, v in by_cat.most_common()],
        "by_district": [{"name": k, "value": v} for k, v in by_dist.most_common(15)],
        "by_hour": by_hour,
        "by_month": [{"period": k, "count": v} for k, v in sorted(by_month.items()) if k],
        "by_status": [{"name": k, "value": v} for k, v in by_status.items()],
    }


@router.get("/timeseries")
@cached(600)
def timeseries(db: Session = Depends(get_session), district=None, crime_type=None, interval="month"):
    cut = {"day": 10, "week": 10, "month": 7}.get(interval, 7)
    period = func.substr(Crime.occurred_at, 1, cut)
    base = _filtered(db, district=district, crime_type=crime_type)
    rows = base.with_entities(period, func.count(Crime.id)).group_by(period).all()
    return {"points": [{"period": k, "count": v} for k, v in sorted(rows) if k]}


# ---- hotspots / emerging / risk -------------------------------------------------------------
@router.get("/hotspots")
@cached(600)
def hotspots(db: Session = Depends(get_session), resolution: int = 8, crime_type=None,
             date_from=None, date_to=None):
    rows = _dicts(_filtered(db, crime_type=crime_type, date_from=date_from, date_to=date_to).all())
    if A_hotspots:
        try:
            return {"cells": _enrich_cells(A_hotspots.compute_hotspots(rows, resolution), rows, resolution)}
        except Exception:
            pass
    # fallback: count per hex + z-score significance
    col = f"h3_r{resolution}" if resolution in (7, 8, 9) else "h3_r8"
    grp = defaultdict(list)
    for r in rows:
        if r.get(col):
            grp[r[col]].append(r)
    counts = {k: len(v) for k, v in grp.items()}
    if not counts:
        return {"cells": []}
    vals = list(counts.values())
    mean = statistics.mean(vals)
    sd = statistics.pstdev(vals) or 1
    cells = []
    for hidx, c in counts.items():
        z = (c - mean) / sd
        lat, lng = _h3_centroid(hidx)
        if lat is None:
            lat, lng = grp[hidx][0]["latitude"], grp[hidx][0]["longitude"]
        cells.append({"h3": hidx, "count": c, "gi_score": round(z, 2),
                      "significance": round(min(1.0, abs(z) / 3), 2),
                      "level": "hot" if z > 1.5 else ("cold" if z < -1.0 else "none"),
                      "lat": lat, "lng": lng})
    return {"cells": sorted(cells, key=lambda x: -x["count"])}


@router.get("/emerging")
@cached(600)
def emerging(db: Session = Depends(get_session), resolution: int = 8, period_days: int = 90):
    rows = _dicts(db.query(Crime).all())
    if A_hotspots and hasattr(A_hotspots, "emerging_hotspots"):
        try:
            return {"cells": _enrich_cells(A_hotspots.emerging_hotspots(rows, resolution, period_days), rows, resolution)}
        except Exception:
            pass
    col = f"h3_r{resolution}" if resolution in (7, 8, 9) else "h3_r8"
    dates = sorted([r["occurred_at"] for r in rows if r["occurred_at"]])
    if not dates:
        return {"cells": []}
    latest = dates[-1][:10]
    from datetime import date
    y, m, d = map(int, latest.split("-"))
    cutoff = (date(y, m, d).toordinal() - period_days)
    recent, base = Counter(), Counter()
    centro = {}
    for r in rows:
        if not r.get(col) or not r["occurred_at"]:
            continue
        yy, mm, dd = map(int, r["occurred_at"][:10].split("-"))
        o = date(yy, mm, dd).toordinal()
        centro.setdefault(r[col], (r["latitude"], r["longitude"]))
        (recent if o >= cutoff else base)[r[col]] += 1
    cells = []
    for hidx in set(list(recent) + list(base)):
        rec, bas = recent.get(hidx, 0), base.get(hidx, 0)
        change = (rec - bas / max(1, (len(dates) / period_days - 1))) if bas else rec
        if rec >= 3 and bas == 0:
            cat = "new"
        elif rec > bas * 1.3 and rec >= 3:
            cat = "intensifying"
        elif rec > 0 and bas > 0 and 0.7 <= rec / max(1, bas) <= 1.3:
            cat = "persistent"
        elif rec < bas * 0.6:
            cat = "diminishing"
        elif rec > 0:
            cat = "sporadic"
        else:
            cat = "none"
        lat, lng = centro.get(hidx, (None, None))
        cells.append({"h3": hidx, "lat": lat, "lng": lng, "category": cat,
                      "recent": rec, "baseline": bas,
                      "change_pct": round(100 * change / max(1, bas), 1) if bas else None})
    return {"cells": [c for c in cells if c["category"] != "none"]}


@router.get("/risk")
@cached(600)
def risk(db: Session = Depends(get_session), resolution: int = 8):
    rows = _dicts(db.query(Crime).all())
    if A_risk:
        try:
            return {"cells": _enrich_cells(A_risk.risk_scores(rows, resolution), rows, resolution)}
        except Exception:
            pass
    col = f"h3_r{resolution}" if resolution in (7, 8, 9) else "h3_r8"
    grp = defaultdict(list)
    for r in rows:
        if r.get(col):
            grp[r[col]].append(r)
    mx = max((len(v) for v in grp.values()), default=1)
    cells = []
    for hidx, items in grp.items():
        night = sum(1 for r in items if (r["hour"] or 12) >= 20 or (r["hour"] or 12) <= 5)
        risk_v = round(0.6 * len(items) / mx + 0.4 * night / max(1, len(items)), 3)
        lat, lng = items[0]["latitude"], items[0]["longitude"]
        drivers = []
        if night / max(1, len(items)) > 0.4:
            drivers.append("high night-time concentration")
        topt = Counter(r["crime_type"] for r in items).most_common(1)[0][0]
        drivers.append(f"recurring {topt}")
        cells.append({"h3": hidx, "lat": lat, "lng": lng, "risk": risk_v, "drivers": drivers})
    return {"cells": sorted(cells, key=lambda x: -x["risk"])}


@router.get("/anomalies")
def anomalies(db: Session = Depends(get_session), limit: int = 50):
    rows = _dicts(db.query(Crime).all())
    if A_anomaly:
        try:
            return {"items": A_anomaly.detect_anomalies(rows, limit)}
        except Exception:
            pass
    # fallback: unusually high property value or odd hour
    vals = [r["property_value_inr"] or 0 for r in rows]
    mean = statistics.mean(vals) if vals else 0
    sd = statistics.pstdev(vals) or 1
    out = []
    for r in rows:
        z = ((r["property_value_inr"] or 0) - mean) / sd
        reasons = []
        if z > 2.5:
            reasons.append("property value far above typical")
        if (r["hour"] or 12) in (2, 3, 4):
            reasons.append("unusual time of occurrence")
        if reasons:
            out.append({"fir_number": r["fir_number"], "score": round(min(1, abs(z) / 4), 2),
                        "reasons": reasons, **r})
    return {"items": sorted(out, key=lambda x: -x["score"])[:limit]}


# ---- network / ER / MO ----------------------------------------------------------------------
@router.get("/network")
@cached(600)
def network(db: Session = Depends(get_session), fir=None, person=None, depth: int = 1, limit: int = 400):
    try:
        return _network_impl(db, fir=fir, person=person, depth=depth, limit=limit)
    except Exception:
        logger.exception("Error in /network fir=%s person=%s depth=%s", fir, person, depth)
        raise


def _network_impl(db, fir=None, person=None, depth=1, limit=400):
    # seed firs
    if fir:
        firs = {fir}
    elif person:
        tokens = [t for t in person.split() if len(t) > 1]
        if not tokens:
            firs = set()
        else:
            q = db.query(Person)
            for tok in tokens:
                like = f"%{tok}%"
                q = q.filter((Person.full_name.ilike(like)) | (Person.normalized_name.ilike(like)))
            firs = {p.fir_number for p in q.all()}
    else:
        firs = {c.fir_number for c in db.query(Crime).order_by(Crime.occurred_at.desc()).limit(120).all()}
    # expand by shared persons/vehicles up to depth
    seen_firs = {f for f in firs if f is not None}
    for _ in range(max(0, depth)):
        if not seen_firs:
            break
        persons = db.query(Person).filter(Person.fir_number.in_(seen_firs)).all()
        ids = {p.true_identity_id for p in persons if p.true_identity_id is not None}
        if ids:
            more = db.query(Person).filter(Person.true_identity_id.in_(ids)).all()
            seen_firs |= {p.fir_number for p in more if p.fir_number is not None}
        if len(seen_firs) > limit:
            break
    seen_firs = set(list(seen_firs)[:limit])
    nodes, edges, seen = [], [], set()

    def add(nid, label, ntype, meta=None):
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "label": label, "type": ntype, "meta": meta or {}})

    crimes_ = db.query(Crime).filter(Crime.fir_number.in_(seen_firs)).all()
    for c in crimes_:
        add(f"crime:{c.fir_number}", c.fir_number, "crime",
            {"type": c.crime_type, "district": c.district, "date": (c.occurred_at or "")[:10]})
        add(f"station:{c.police_station}", c.police_station, "station", {"district": c.district})
        edges.append({"source": f"crime:{c.fir_number}", "target": f"station:{c.police_station}", "label": "at"})
    for p in db.query(Person).filter(Person.fir_number.in_(seen_firs)).all():
        pid = f"person:{p.true_identity_id}"
        add(pid, p.full_name, "person", {"role": p.role, "district": p.district})
        edges.append({"source": pid, "target": f"crime:{p.fir_number}", "label": p.role})
    for v in db.query(Vehicle).filter(Vehicle.fir_number.in_(seen_firs)).all():
        vid = f"vehicle:{v.reg_number}"
        add(vid, v.reg_number, "vehicle", {"vtype": v.vehicle_type})
        edges.append({"source": vid, "target": f"crime:{v.fir_number}", "label": "linked"})
    return {"nodes": nodes, "edges": edges}


@router.get("/network/communities")
def communities(db: Session = Depends(get_session)):
    net = _network_impl(db)  # default ego set
    if A_comm:
        try:
            return {"communities": A_comm.detect_communities(net["nodes"], net["edges"])}
        except Exception:
            pass
    # fallback: connected components via persons sharing crimes
    adj = defaultdict(set)
    for e in net["edges"]:
        adj[e["source"]].add(e["target"])
        adj[e["target"]].add(e["source"])
    seen, comms = set(), []
    for n in net["nodes"]:
        nid = n["id"]
        if nid in seen:
            continue
        stack, group = [nid], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            group.append(x)
            stack.extend(adj[x] - seen)
        if len(group) >= 4:
            comms.append({"id": len(comms), "members": group, "size": len(group),
                          "key_nodes": sorted(group, key=lambda g: -len(adj[g]))[:3]})
    return {"communities": sorted(comms, key=lambda c: -c["size"])[:20]}


@router.get("/entity-resolution")
@cached(600)
def entity_resolution(db: Session = Depends(get_session), threshold: float = 0.82, limit: int = 300):
    # Cap the working set for the free-tier instance: loading all ~100k persons
    # took ~38s (gateway-timeout territory). Order by normalized_name so alias
    # clusters stay adjacent — matches are still found within the capped window.
    persons = _dicts(db.query(Person).order_by(Person.normalized_name).limit(6000).all())
    if A_er:
        try:
            pairs = A_er.resolve_entities(persons, threshold)
            return {"total": len(pairs), "pairs": pairs[:limit]}
        except Exception:
            pass
    # fallback: rapidfuzz on normalized names
    try:
        from rapidfuzz import fuzz
    except Exception:
        return {"total": 0, "pairs": []}
    pairs, seen = [], set()
    by_first = defaultdict(list)
    for p in persons:
        key = (p["normalized_name"] or p["full_name"] or "")[:3].lower()
        by_first[key].append(p)
    for bucket in by_first.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                if a["fir_number"] == b["fir_number"]:
                    continue
                s = fuzz.token_sort_ratio(a["full_name"], b["full_name"]) / 100
                phone_match = a.get("phone") and a.get("phone") == b.get("phone")
                if phone_match:
                    s = max(s, 0.9)
                if s >= threshold:
                    k = tuple(sorted([a["person_id"], b["person_id"]]))
                    if k in seen:
                        continue
                    seen.add(k)
                    ev = [f"name similarity {s:.2f}"]
                    if phone_match:
                        ev.append("identical phone number")
                    pairs.append({"a": a["full_name"], "b": b["full_name"],
                                  "a_fir": a["fir_number"], "b_fir": b["fir_number"],
                                  "score": round(s, 3), "evidence": ev,
                                  "decision": "auto" if s >= 0.95 or phone_match else "review"})
    pairs = sorted(pairs, key=lambda x: -x["score"])
    return {"total": len(pairs), "pairs": pairs[:limit]}


@router.get("/mo-linkage")
@cached(600)
def mo_linkage(db: Session = Depends(get_session), fir: str = Query(...), top_k: int = 10):
    target = db.query(Crime).filter(Crime.fir_number == fir).first()
    if not target:
        return {"target": fir, "matches": []}
    rows = _dicts(db.query(Crime).filter(Crime.crime_category == target.crime_category).all())
    if A_mo:
        try:
            return {"target": fir, "matches": A_mo.link_by_mo(target.as_dict(), rows, top_k)}
        except Exception:
            pass
    tgt_terms = set((target.modus_operandi or "").lower().split())
    out = []
    for r in rows:
        if r["fir_number"] == fir:
            continue
        terms = set((r["modus_operandi"] or "").lower().split())
        inter = tgt_terms & terms
        union = tgt_terms | terms
        sim = len(inter) / len(union) if union else 0
        if sim > 0:
            out.append({"fir_number": r["fir_number"], "similarity": round(sim, 3),
                        "shared_terms": sorted(inter)[:8], **r})
    return {"target": fir, "matches": sorted(out, key=lambda x: -x["similarity"])[:top_k]}


# ---- assistant ------------------------------------------------------------------------------
@router.post("/assistant/chat")
def chat(payload: dict, db: Session = Depends(get_session)):
    msg = (payload or {}).get("message", "")
    filt = assistant.parse_intent(msg)
    rows = _dicts(_filtered(db, district=filt.get("district"), crime_type=filt.get("crime_type"),
                            category=filt.get("category"), date_from=filt.get("date_from"),
                            date_to=filt.get("date_to"), q=filt.get("q")).limit(800).all())
    if filt.get("hour_min") is not None:
        rows = [r for r in rows if (r["hour"] or 0) >= filt["hour_min"]]
    return assistant.answer(msg, rows, filt)


# ---- MyShield (citizen self-check) ----------------------------------------------------------
@router.get("/myshield")
def myshield(db: Session = Depends(get_session), identifier: str = Query(...), token: str = "demo"):
    ident = identifier.strip()
    matches = []
    persons = db.query(Person).filter((Person.phone == ident) | (Person.full_name.ilike(ident))).all()
    veh = db.query(Vehicle).filter(Vehicle.reg_number.ilike(ident)).all()
    firs = {p.fir_number for p in persons} | {v.fir_number for v in veh}
    district = persons[0].district if persons else None
    for c in db.query(Crime).filter(Crime.fir_number.in_(firs)).all():
        matches.append({"fir_number": c.fir_number, "crime_type": c.crime_type,
                        "police_station": c.police_station, "date": (c.occurred_at or "")[:10],
                        "status": c.status})
    area = {}
    if district:
        rows = db.query(Crime).filter(Crime.district == district).all()
        area = {"district": district,
                "counts_by_type": dict(Counter(c.crime_type for c in rows).most_common(6)),
                "total_in_district": len(rows)}
    return {"matches": matches, "area_safety": area,
            "disclaimer": ("Demo only. In production this requires DigiLocker/Aadhaar eKYC. "
                           "Only your own verified records and de-identified area statistics are ever shown.")}


# ---- ingestion (connect your own dataset) ---------------------------------------------------
@router.post("/ingest")
async def ingest(file: UploadFile = File(...), mapping: str = Form("{}"),
                 db: Session = Depends(get_session)):
    raw = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw))
        elif name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw))
        elif name.endswith(".ndjson"):
            df = pd.read_json(io.BytesIO(raw), lines=True)
        elif name.endswith(".geojson"):
            gj = json.loads(raw)
            recs = []
            for ft in gj.get("features", []):
                props = ft.get("properties", {})
                geom = ft.get("geometry", {}) or {}
                if geom.get("type") == "Point":
                    props["longitude"], props["latitude"] = geom["coordinates"][:2]
                recs.append(props)
            df = pd.DataFrame(recs)
        else:
            df = pd.read_json(io.BytesIO(raw))
    except Exception as e:
        return {"inserted": 0, "skipped": 0, "missing_report": {}, "errors": [f"parse error: {e}"]}

    colmap = json.loads(mapping or "{}")
    if colmap:
        df = df.rename(columns=colmap)

    inserted, skipped, errors = 0, 0, []
    missing = Counter()
    for _, row in df.iterrows():
        d = {k: (row[k] if k in row and pd.notna(row[k]) else None) for k in Crime.COLS}
        if not d.get("fir_number"):
            d["fir_number"] = f"ING{inserted+skipped:08d}"
        for k in Crime.COLS:
            if d.get(k) in (None, ""):
                missing[k] += 1
        if d.get("latitude") and d.get("longitude") and h3 and not d.get("h3_r8"):
            try:
                for res in (7, 8, 9):
                    d[f"h3_r{res}"] = h3.latlng_to_cell(float(d["latitude"]), float(d["longitude"]), res)
            except Exception:
                pass
        try:
            if db.query(Crime).filter(Crime.fir_number == d["fir_number"]).first():
                skipped += 1
                continue
            db.add(Crime(**d))
            inserted += 1
        except Exception as e:
            errors.append(str(e))
            skipped += 1
    db.commit()
    _cache_clear()  # new records invalidate cached analytics responses
    return {"inserted": inserted, "skipped": skipped,
            "missing_report": {k: v for k, v in missing.most_common() if v},
            "errors": errors[:5],
            "note": "Missing fields are reported, never auto-filled (zero-fabrication policy)."}


# ============================================================================================
#  EXTENDED FEATURES
# ============================================================================================

# ---- NLP on FIR narratives ------------------------------------------------------------------
@router.get("/nlp/extract")
def nlp_extract(fir: str = Query(...), db: Session = Depends(get_session)):
    c = db.query(Crime).filter(Crime.fir_number == fir).first()
    if not c:
        return {"fir": fir, "entities": {}, "keywords": [], "summary": "FIR not found."}
    if A_nlp:
        try:
            return {"fir": fir, **A_nlp.extract_entities(c.as_dict())}
        except Exception:
            pass
    return {"fir": fir, "entities": {}, "keywords": [], "summary": (c.modus_operandi or "")[:160]}


# ---- CDR analysis ---------------------------------------------------------------------------
def _cdr_rows(db):
    # Alias columns to the names the CDR analytics module recognises.
    out = []
    for r in db.query(CDR).all():
        d = r.as_dict()
        d["caller"] = d.get("caller_msisdn")
        d["callee"] = d.get("callee_msisdn")
        d["tower"] = d.get("cell_tower_id")
        d["duration"] = d.get("duration_sec")
        out.append(d)
    return out


@router.get("/cdr/sample")
def cdr_sample(db: Session = Depends(get_session)):
    # Return a high-activity number + busy tower so the demo lands on rich data.
    top = (db.query(CDR.caller_msisdn, func.count(CDR.id).label("c"))
           .group_by(CDR.caller_msisdn).order_by(func.count(CDR.id).desc()).first())
    twr = (db.query(CDR.cell_tower_id, func.count(CDR.id).label("c"))
           .group_by(CDR.cell_tower_id).order_by(func.count(CDR.id).desc()).first())
    return {"msisdn": top[0] if top else None, "tower": twr[0] if twr else None}


@router.get("/cdr/contacts")
@cached(600)
def cdr_contacts(msisdn: str = Query(...), db: Session = Depends(get_session)):
    if A_cdr:
        try:
            return A_cdr.cdr_contacts(_cdr_rows(db), msisdn)
        except Exception:
            pass
    return {"msisdn": msisdn, "total_calls": 0, "top_contacts": [], "common_towers": [], "co_location": []}


@router.get("/cdr/network")
@cached(600)
def cdr_network(msisdn: str = Query(...), depth: int = 1, db: Session = Depends(get_session)):
    if A_cdr:
        try:
            return A_cdr.cdr_network(_cdr_rows(db), msisdn, depth)
        except Exception:
            pass
    return {"nodes": [], "edges": []}


@router.get("/cdr/tower-dump")
def cdr_tower_dump(tower: str = Query(...), start: str = None, end: str = None,
                   db: Session = Depends(get_session)):
    if A_cdr:
        try:
            return A_cdr.tower_dump(_cdr_rows(db), tower, start, end)
        except Exception:
            pass
    return {"tower": tower, "numbers": []}


# ---- Cybercrime / financial fraud -----------------------------------------------------------
@router.get("/cyber/overview")
@cached(600)
def cyber_overview(db: Session = Depends(get_session)):
    try:
        crimes = [r.as_dict() for r in db.query(Crime).filter(Crime.crime_category == "Cybercrime").all()]
    except Exception:
        logger.exception("cyber_overview: DB query failed")
        raise
    if A_cyber:
        try:
            result = A_cyber.cyber_overview(crimes)
            try:
                accounts = [r.as_dict() for r in db.query(Account).all()]
                txns = [r.as_dict() for r in db.query(Transaction).all()]
                result.setdefault("kpis", {})["mule_accounts"] = len(A_cyber.detect_mules(accounts, txns, limit=10000))
            except Exception:
                logger.exception("cyber_overview: mule augmentation failed")
            return result
        except Exception:
            logger.exception("cyber_overview: A_cyber.cyber_overview failed")
    return {"kpis": {"total_cases": len(crimes), "total_loss": 0, "mule_accounts": 0, "recovery_rate": 0.0},
            "by_type": [], "trend": [], "top_districts": []}


@router.get("/cyber/mules")
@cached(600)
def cyber_mules(limit: int = 50, db: Session = Depends(get_session)):
    if A_cyber:
        try:
            accounts = [r.as_dict() for r in db.query(Account).all()]
            txns = [r.as_dict() for r in db.query(Transaction).all()]
            items = A_cyber.detect_mules(accounts, txns, limit)
            return {"total": len(items), "items": items}
        except Exception:
            pass
    return {"total": 0, "items": []}


@router.get("/cyber/money-flow")
@cached(600)
def cyber_money_flow(account: str = Query(...), depth: int = 2, db: Session = Depends(get_session)):
    if A_cyber:
        try:
            accounts = [r.as_dict() for r in db.query(Account).all()]
            txns = [r.as_dict() for r in db.query(Transaction).all()]
            return A_cyber.money_flow(txns, accounts, account, depth)
        except Exception:
            pass
    return {"nodes": [], "edges": []}


@router.get("/cyber/sample")
def cyber_sample(db: Session = Depends(get_session)):
    t = db.query(Transaction).filter(Transaction.is_flagged.is_(True)).first()
    if t:
        return {"account": t.from_account}
    a = db.query(Account).first()
    return {"account": a.account_id if a else None}


# ---- Missing persons ------------------------------------------------------------------------
@router.get("/missing/cases")
def missing_cases(status: str = None, risk: str = None, db: Session = Depends(get_session)):
    q = db.query(MissingPerson)
    if status:
        q = q.filter(MissingPerson.status == status)
    if risk:
        q = q.filter(MissingPerson.risk_tier == risk)
    return {"items": [r.as_dict() for r in q.all()]}


# ---- Patrol optimisation (place-based) ------------------------------------------------------
@router.get("/patrol/optimize")
@cached(600)
def patrol_optimize(resolution: int = 8, units: int = 15, db: Session = Depends(get_session)):
    rows = [r.as_dict() for r in db.query(Crime).all()]
    if A_patrol:
        try:
            result = A_patrol.optimize_patrol(rows, resolution, units)
            result["assignments"] = _enrich_cells(result.get("assignments", []), rows, resolution)
            return result
        except Exception:
            pass
    return {"assignments": [], "coverage_pct": 0, "summary": ""}


# ---- Oversight: fairness diagnostics + audit ledger -----------------------------------------
@router.get("/oversight/fairness")
def oversight_fairness(db: Session = Depends(get_session)):
    rows = [r.as_dict() for r in db.query(Crime).all()]
    if A_oversight:
        try:
            return A_oversight.fairness_metrics(rows)
        except Exception:
            pass
    return {"coverage_by_district": [], "category_mix": [], "disparity_flags": []}


@router.get("/oversight/audit")
def oversight_audit(limit: int = 50, db: Session = Depends(get_session)):
    integrity = audit.verify_chain(db)
    rows = db.query(AuditLog).order_by(AuditLog.seq.desc()).limit(limit).all()
    entries = [{"seq": r.seq, "ts": r.ts, "user": r.user, "action": r.action,
                "resource": r.resource, "entry_hash": r.entry_hash} for r in rows]
    return {"entries": entries, "integrity": integrity}


# ---- Network motif detection ----------------------------------------------------------------
@router.get("/network/motifs")
@cached(600)
def network_motifs(depth: int = 1, limit: int = 300, db: Session = Depends(get_session)):
    try:
        from .analytics import motifs as A_motifs
    except Exception:
        return {"triangles": [], "stars": [], "chains": [], "stats": {}, "summary": "Module unavailable."}
    net = network(db, depth=depth, limit=limit)
    try:
        return A_motifs.detect_motifs(net["nodes"], net["edges"])
    except Exception as e:
        return {"triangles": [], "stars": [], "chains": [], "stats": {}, "summary": str(e)}


# ---- ACO patrol optimisation ----------------------------------------------------------------
@router.get("/patrol/aco")
@cached(600)
def patrol_aco(resolution: int = 8, units: int = 15, n_ants: int = 30, n_iter: int = 60,
               db: Session = Depends(get_session)):
    try:
        from .analytics import aco_patrol as A_aco
    except Exception:
        return patrol_optimize(resolution=resolution, units=units, db=db)
    rows = [r.as_dict() for r in db.query(Crime).all()]
    # Re-use the patrol analytics to get scored cells
    if A_patrol:
        try:
            cells_raw = A_patrol.optimize_patrol(rows, resolution, units * 3)["assignments"]
        except Exception:
            cells_raw = []
    else:
        cells_raw = []
    # Convert to {w: risk_weight} format for ACO
    total_w = sum(float(c.get("expected_share") or 0) for c in cells_raw) or 1.0
    cells_for_aco = [dict(c, w=float(c.get("expected_share") or 0)) for c in cells_raw]
    try:
        selected = A_aco.aco_patrol(cells_for_aco, units, n_ants=n_ants, n_iter=n_iter)
        selected = _enrich_cells(selected, rows, resolution)
        covered = sum(float(c.get("expected_share") or 0) for c in selected)
        return {
            "assignments": selected,
            "coverage_pct": round(100.0 * covered / total_w, 1),
            "summary": f"ACO ({n_ants} ants × {n_iter} iterations) allocated {len(selected)} unit(s).",
            "algorithm": "ACO",
        }
    except Exception as e:
        return {"assignments": [], "coverage_pct": 0, "summary": str(e), "algorithm": "ACO"}


# ---- Differential privacy hotspots ----------------------------------------------------------
@router.get("/hotspots/dp")
@cached(600)
def hotspots_dp(epsilon: float = 1.0, resolution: int = 8,
                crime_type: str = None, db: Session = Depends(get_session)):
    try:
        from .analytics import dp_hotspot as A_dp
    except Exception:
        return hotspots(db=db, resolution=resolution, crime_type=crime_type)
    raw = hotspots(db=db, resolution=resolution, crime_type=crime_type)
    cells = raw.get("cells", [])
    try:
        result = A_dp.privatise_hotspots(cells, epsilon=max(0.05, min(20.0, float(epsilon))))
        return result
    except Exception as e:
        return {"cells": cells, "epsilon": epsilon, "error": str(e)}


# ---- Geographic profiling (Rossmo CGT) -------------------------------------------------------
@router.get("/geo-profile")
@cached(600)
def geo_profile(crime_type: str = None, date_from: str = None, date_to: str = None,
                resolution: int = 60, db: Session = Depends(get_session)):
    try:
        from .analytics import geoprofiling as A_gp
    except Exception:
        return {"points": [], "anchor": None, "total_crimes": 0, "unique_locs": 0, "params": {}}
    # Cap the working set: the Rossmo surface is O(grid^2 * points), so on the
    # constrained free-tier AppSail instance we keep both bounded to stay well
    # within memory/CPU/timeout limits while preserving a representative surface.
    rows = _dicts(
        _filtered(db, crime_type=crime_type, date_from=date_from, date_to=date_to)
        .filter(Crime.latitude.isnot(None), Crime.longitude.isnot(None))
        .limit(600).all()
    )
    try:
        return A_gp.rossmo_surface(rows, grid_steps=min(45, max(25, int(resolution or 40))),
                                   max_points=500)
    except Exception as e:
        return {"points": [], "anchor": None, "total_crimes": len(rows), "unique_locs": 0,
                "params": {}, "error": str(e)}


# ---- Crime forecasting (Holt ETS) -----------------------------------------------------------
@router.get("/forecast")
@cached(600)
def forecast_view(crime_type: str = None, district: str = None, months: int = 3,
                  db: Session = Depends(get_session)):
    try:
        from .analytics import forecasting as A_fc
    except Exception:
        return {"history": [], "forecast": [], "trend": "stable", "model": "N/A", "rmse": 0}
    rows = _dicts(_filtered(db, crime_type=crime_type, district=district).all())
    bucket: Counter = Counter()
    for r in rows:
        key = (r.get("occurred_at") or "")[:7]
        if key and len(key) == 7:
            bucket[key] += 1
    pts = [{"period": k, "count": v} for k, v in sorted(bucket.items())]
    try:
        return A_fc.forecast_crimes(pts, horizon=min(12, max(1, int(months or 3))))
    except Exception as e:
        return {"history": pts, "forecast": [], "trend": "stable", "model": "error", "rmse": 0,
                "error": str(e)}


# ---- Near-repeat risk -----------------------------------------------------------------------
@router.get("/near-repeat")
@cached(600)
def near_repeat(crime_type: str = None, days: int = 14, db: Session = Depends(get_session)):
    try:
        from .analytics import forecasting as A_fc
    except Exception:
        return {"alerts": []}
    rows = _dicts(_filtered(db, crime_type=crime_type).order_by(Crime.occurred_at.desc()).limit(2000).all())
    try:
        alerts = A_fc.near_repeat_risk(rows, days_window=int(days or 14))
        return {"alerts": alerts}
    except Exception:
        return {"alerts": []}


# ---- Temporal analysis (day × hour matrix) --------------------------------------------------
@router.get("/temporal")
@cached(600)
def temporal(district: str = None, crime_type: str = None, db: Session = Depends(get_session)):
    import datetime
    rows = _dicts(_filtered(db, district=district, crime_type=crime_type).all())
    matrix = [[0] * 24 for _ in range(7)]
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for r in rows:
        occ = r.get("occurred_at")
        hour = r.get("hour")
        if occ and hour is not None:
            try:
                parts = str(occ)[:10].split("-")
                d = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
                matrix[d.weekday()][int(hour)] += 1
            except Exception:
                pass
    # Calendar heatmap data (by date)
    by_date: Counter = Counter()
    for r in rows:
        day = (r.get("occurred_at") or "")[:10]
        if len(day) == 10:
            by_date[day] += 1
    return {
        "matrix": [{"day": dow_names[i], "hours": matrix[i]} for i in range(7)],
        "calendar": [{"date": k, "count": v} for k, v in sorted(by_date.items())],
        "total": sum(sum(row) for row in matrix),
    }


# ---- Suspect intelligence (deep person profile) ---------------------------------------------
@router.get("/suspect/profile")
@cached(600)
def suspect_profile(name: str = Query(...), db: Session = Depends(get_session)):
    tokens = [t for t in name.split() if len(t) > 1]
    _pq = db.query(Person)
    for _tok in tokens:
        _like = f"%{_tok}%"
        _pq = _pq.filter((Person.full_name.ilike(_like)) | (Person.normalized_name.ilike(_like)))
    persons = (_pq.limit(200).all() if tokens else [])
    if not persons:
        return {"name": name, "matches": [], "firs": [], "stats": {}, "vehicles": []}
    tids = list({p.true_identity_id for p in persons if p.true_identity_id})
    all_p = (db.query(Person).filter(Person.true_identity_id.in_(tids)).all()
             if tids else list(persons))
    fir_nos = list({p.fir_number for p in all_p})[:200]
    crimes_ = db.query(Crime).filter(Crime.fir_number.in_(fir_nos)).all()
    by_type: Counter = Counter(c.crime_type for c in crimes_)
    by_role: Counter = Counter(p.role for p in all_p)
    by_district: Counter = Counter(c.district for c in crimes_)
    by_hour = [0] * 24
    for c in crimes_:
        if c.hour is not None:
            try:
                by_hour[int(c.hour)] += 1
            except Exception:
                pass
    return {
        "name": name,
        "matches": [{"name": p.full_name, "role": p.role, "fir": p.fir_number,
                     "tid": p.true_identity_id} for p in persons[:30]],
        "firs": [{"fir_number": c.fir_number, "crime_type": c.crime_type,
                  "district": c.district, "occurred_at": (c.occurred_at or "")[:10],
                  "status": c.status, "lat": c.latitude, "lng": c.longitude,
                  "property_value_inr": c.property_value_inr}
                 for c in crimes_[:60]],
        "stats": {
            "total_firs": len(fir_nos),
            "unique_identities": len(tids) or len(persons),
            "top_type": by_type.most_common(1)[0][0] if by_type else None,
            "by_type": [{"name": k, "value": v} for k, v in by_type.most_common(8)],
            "by_role": [{"name": k, "value": v} for k, v in by_role.most_common()],
            "by_district": [{"name": k, "value": v} for k, v in by_district.most_common(6)],
            "by_hour": by_hour,
        },
        "vehicles": [{"reg": v.reg_number, "type": v.vehicle_type, "fir": v.fir_number}
                     for v in db.query(Vehicle).filter(Vehicle.fir_number.in_(fir_nos)).all()[:20]],
    }


# ---- Case correlation (multi-signal clustering) --------------------------------------------
@router.get("/cases/correlate")
def cases_correlate(crime_type: str = None, district: str = None,
                    threshold: float = 4.0, limit: int = 500,
                    db: Session = Depends(get_session)):
    try:
        from .analytics import correlate as A_corr
    except Exception:
        return {"clusters": [], "total_crimes": 0, "total_linked": 0,
                "method": "unavailable", "threshold": threshold}
    q = db.query(Crime)
    if crime_type:
        q = q.filter(Crime.crime_type == crime_type)
    if district:
        q = q.filter(Crime.district == district)
    rows = [r.as_dict() for r in q.limit(limit).all()]
    persons = [p.as_dict() for p in db.query(Person).limit(limit * 3).all()]
    vehicles = [v.as_dict() for v in db.query(Vehicle).limit(limit * 2).all()]
    try:
        return A_corr.correlate_cases(rows, persons, vehicles,
                                      threshold=max(1.0, min(10.0, threshold)))
    except Exception as e:
        return {"clusters": [], "total_crimes": len(rows), "total_linked": 0,
                "method": "error", "threshold": threshold, "error": str(e)}


# ---- Behavioral analytics (criminal career profile) -----------------------------------------
@router.get("/suspect/behavior")
@cached(600)
def suspect_behavior(name: str = Query(...), db: Session = Depends(get_session)):
    try:
        from .analytics import behavioral as A_beh
    except Exception:
        return {"found": False, "name": name, "error": "Module unavailable."}
    crimes_ = [r.as_dict() for r in db.query(Crime).all()]
    persons_ = [p.as_dict() for p in db.query(Person).all()]
    try:
        return A_beh.criminal_profile(crimes_, persons_, name)
    except Exception as e:
        return {"found": False, "name": name, "error": str(e)}


# ---- Auto-drafted, grounded intelligence briefing -------------------------------------------
@router.get("/briefing")
def briefing(district: str = None, limit: int = 400, db: Session = Depends(get_session)):
    """Grounded briefing = a GENERAL situational summary (sections) PLUS a
    per-FIR brief for every FIR in scope, each expandable in the UI."""
    s = stats(db, district=district)
    hs = hotspots(db, resolution=8).get("cells", [])[:20]
    em = emerging(db).get("cells", [])
    an = anomalies(db, limit=10).get("items", [])
    lim = max(1, min(1000, int(limit or 400)))
    scope_q = _filtered(db, district=district)
    real_total = scope_q.count()
    crimes = _dicts(scope_q.order_by(Crime.occurred_at.desc()).limit(lim).all())
    if A_briefing:
        try:
            out = A_briefing.generate_briefing(s, hs, em, an, district)
            out["fir_briefs"] = A_briefing.per_fir_briefs(crimes, limit=lim, total=real_total)
            return out
        except Exception as e:
            logger.warning("briefing failed: %s", e)
    return {"generated_at": "", "headline": "Briefing unavailable", "sections": [], "fir_briefs": {}}


# ============================================================================================
# KSP FIR-schema analytics — served from the official CCTNS-aligned normalized tables
# (CaseMaster / ActSectionAssociation / Court / Employee / Unit ...). These prove the ER
# schema is not just present but queryable end-to-end. All read-only; degrade to empty if the
# KSP tables haven't been built yet (build_ksp_schema.py).
# ============================================================================================
from sqlalchemy import text as _sql


def _ksp(sql, params=None):
    """Run raw SQL against the KSP normalized tables; return list[dict]. Empty on any error."""
    try:
        with engine.connect() as c:
            res = c.execute(_sql(sql), params or {})
            cols = list(res.keys())
            return [dict(zip(cols, row)) for row in res.fetchall()]
    except Exception as e:
        logger.warning("KSP query failed: %s", e)
        return []


@router.get("/ksp/legal")
def ksp_legal(db: Session = Depends(get_session)):
    """Act & Section breakdown from ActSectionAssociation (the charges applied to each FIR)."""
    by_act = _ksp("""
        SELECT COALESCE(a.ShortName, asa.ActID) AS name,
               COALESCE(a.ActDescription, asa.ActID) AS full_name,
               COUNT(*) AS value
        FROM ActSectionAssociation asa
        LEFT JOIN Act a ON a.ActCode = asa.ActID
        GROUP BY name, full_name ORDER BY value DESC""")
    by_section = _ksp("""
        SELECT asa.ActID AS act, asa.SectionID AS section,
               COALESCE(s.SectionDescription, '') AS description,
               COUNT(*) AS value
        FROM ActSectionAssociation asa
        LEFT JOIN Section s ON s.ActCode = asa.ActID AND s.SectionCode = asa.SectionID
        GROUP BY asa.ActID, asa.SectionID, description
        ORDER BY value DESC LIMIT 15""")
    tot = sum(r["value"] for r in by_act)
    return {
        "kpis": {
            "total_charges": tot,
            "distinct_acts": len(by_act),
            "distinct_sections": len(_ksp("SELECT DISTINCT ActID, SectionID FROM ActSectionAssociation")),
            "top_act": (by_act[0]["name"] if by_act else "—"),
        },
        "by_act": by_act,
        "by_section": by_section,
    }


@router.get("/ksp/court-pendency")
def ksp_court_pendency(db: Session = Depends(get_session)):
    """Case-status funnel and court-wise pendency vs disposal from CaseMaster + Court."""
    by_status = _ksp("""
        SELECT COALESCE(sm.CaseStatusName,'Unknown') AS name, COUNT(*) AS value
        FROM CaseMaster cm LEFT JOIN CaseStatusMaster sm ON sm.CaseStatusID = cm.CaseStatusID
        GROUP BY name ORDER BY value DESC""")
    disposed_set = ("Charge Sheeted", "Closed")
    by_court = _ksp("""
        SELECT co.CourtName AS name,
               SUM(CASE WHEN sm.CaseStatusName IN ('Charge Sheeted','Closed') THEN 1 ELSE 0 END) AS disposed,
               SUM(CASE WHEN sm.CaseStatusName NOT IN ('Charge Sheeted','Closed') OR sm.CaseStatusName IS NULL THEN 1 ELSE 0 END) AS pending,
               COUNT(*) AS total
        FROM CaseMaster cm
        LEFT JOIN Court co ON co.CourtID = cm.CourtID
        LEFT JOIN CaseStatusMaster sm ON sm.CaseStatusID = cm.CaseStatusID
        WHERE co.CourtName IS NOT NULL
        GROUP BY co.CourtName ORDER BY total DESC LIMIT 15""")
    total = sum(r["value"] for r in by_status)
    disposed = sum(r["value"] for r in by_status if r["name"] in disposed_set)
    chargesheets = _ksp("SELECT COUNT(*) AS n FROM ChargesheetDetails")
    return {
        "kpis": {
            "total_cases": total,
            "pending": total - disposed,
            "disposed": disposed,
            "disposal_rate": round(100 * disposed / total, 1) if total else 0,
            "chargesheets_filed": (chargesheets[0]["n"] if chargesheets else 0),
        },
        "by_status": by_status,
        "by_court": by_court,
    }


@router.get("/ksp/officer-workload")
def ksp_officer_workload(db: Session = Depends(get_session)):
    """Per-officer (registering officer) and per-station caseload from Employee + Unit + CaseMaster."""
    by_officer = _ksp("""
        SELECT e.FirstName AS name, r.RankName AS rank, u.UnitName AS station,
               COUNT(*) AS cases,
               SUM(CASE WHEN sm.CaseStatusName IN ('Charge Sheeted','Closed') THEN 1 ELSE 0 END) AS disposed
        FROM CaseMaster cm
        JOIN Employee e ON e.EmployeeID = cm.PolicePersonID
        LEFT JOIN Rank r ON r.RankID = e.RankID
        LEFT JOIN Unit u ON u.UnitID = e.UnitID
        LEFT JOIN CaseStatusMaster sm ON sm.CaseStatusID = cm.CaseStatusID
        GROUP BY e.EmployeeID ORDER BY cases DESC LIMIT 15""")
    by_station = _ksp("""
        SELECT u.UnitName AS name, d.DistrictName AS district, COUNT(*) AS value
        FROM CaseMaster cm
        JOIN Unit u ON u.UnitID = cm.PoliceStationID
        LEFT JOIN District d ON d.DistrictID = u.DistrictID
        GROUP BY u.UnitID ORDER BY value DESC LIMIT 15""")
    officers = _ksp("SELECT COUNT(DISTINCT PolicePersonID) AS n FROM CaseMaster WHERE PolicePersonID IS NOT NULL")
    stations = _ksp("SELECT COUNT(DISTINCT PoliceStationID) AS n FROM CaseMaster WHERE PoliceStationID IS NOT NULL")
    total = _ksp("SELECT COUNT(*) AS n FROM CaseMaster")
    n_off = officers[0]["n"] if officers else 0
    n_tot = total[0]["n"] if total else 0
    for o in by_officer:
        o["clearance"] = round(100 * (o.get("disposed") or 0) / o["cases"], 1) if o["cases"] else 0
    return {
        "kpis": {
            "officers": n_off,
            "stations": (stations[0]["n"] if stations else 0),
            "avg_caseload": round(n_tot / n_off, 1) if n_off else 0,
            "busiest_station": (by_station[0]["name"] if by_station else "—"),
        },
        "by_officer": by_officer,
        "by_station": by_station,
    }
