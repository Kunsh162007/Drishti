"""Production API: every intelligence endpoint is authenticated (JWT/RBAC) and
written to the tamper-evident audit ledger. DB I/O lives here; the heavy analytics
are the SAME pure functions used by the demo (imported from the shared package),
so behaviour is identical — only the infrastructure (Postgres/Neo4j/Qdrant/LLM)
and the security wrapper change.
"""
from __future__ import annotations

import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Query, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from .config import settings  # noqa: E402
from .db import get_session  # noqa: E402
from .models import (Crime, Person, Vehicle, CDR, Account, Transaction,  # noqa: E402
                     MissingPerson, User, AuditLog)
from .security import auth, audit, encryption  # noqa: E402
from .security.auth import get_current_user, require_role  # noqa: E402
from .services import graph_neo4j, vector_rag, entity_resolution_splink  # noqa: E402

# Shared pure analytics (records in -> results out). Imported defensively.
try:
    from demo.backend.analytics import (hotspots as A_hot, anomaly as A_anom, mo_linkage as A_mo,
                                        risk as A_risk, communities as A_comm, nlp_extract as A_nlp,
                                        cdr as A_cdr, cyber as A_cyber, patrol as A_patrol,
                                        oversight as A_over, briefing as A_brief)
except Exception:  # pragma: no cover
    A_hot = A_anom = A_mo = A_risk = A_comm = A_nlp = A_cdr = A_cyber = A_patrol = A_over = A_brief = None

try:
    import h3
except Exception:
    h3 = None


# ============================================================ public (no auth) ==
public = APIRouter()


@public.get("/health")
def health(db: Session = Depends(get_session)):
    return {"status": "ok", "env": settings.ENV, "db": settings.DATABASE_URL.split("://")[0],
            "records": db.query(func.count(Crime.id)).scalar() or 0}


@public.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)):
    user = auth.authenticate_user(db, form.username, form.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    audit.append(db, user.username, "LOGIN", "/auth/login", "")
    token = auth.create_access_token(user.username, user.role)
    return {"access_token": token, "token_type": "bearer", "role": user.role}


@public.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"username": user.username, "role": user.role, "full_name": user.full_name}


# ---- /api-prefixed public aliases so the shared SPA (api.js uses /api) works ----------------
@public.get("/api/health")
def health_api(db: Session = Depends(get_session)):
    return health(db)


@public.post("/api/auth/login")
def login_api(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)):
    return login(form, db)


@public.get("/api/auth/me")
def me_api(user: User = Depends(get_current_user)):
    return me(user)


# ===================================================== protected (auth+audit) ==
def audit_dep(request: Request, user: User = Depends(get_current_user),
              db: Session = Depends(get_session)) -> User:
    try:
        audit.append(db, user.username, request.method, request.url.path,
                     str(dict(request.query_params))[:180])
    except Exception:
        pass
    return user


api = APIRouter(prefix="/api", dependencies=[Depends(audit_dep)])


# ---- helpers --------------------------------------------------------------------------------
def _filtered(db, district=None, crime_type=None, category=None, date_from=None, date_to=None, q=None):
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
        query = query.filter((Crime.modus_operandi.like(like)) | (Crime.fir_number.like(like)))
    return query


def _crimes(db, **kw):
    return [r.as_dict() for r in _filtered(db, **kw).all()]


def _cdr_rows(db):
    out = []
    for r in db.query(CDR).all():
        d = r.as_dict()
        d["caller"], d["callee"] = d.get("caller_msisdn"), d.get("callee_msisdn")
        d["tower"], d["duration"] = d.get("cell_tower_id"), d.get("duration_sec")
        out.append(d)
    return out


# ---- meta / crimes / stats ------------------------------------------------------------------
@api.get("/meta")
def meta(db: Session = Depends(get_session)):
    districts = [d[0] for d in db.query(Crime.district).distinct().order_by(Crime.district)]
    types = [t[0] for t in db.query(Crime.crime_type).distinct().order_by(Crime.crime_type)]
    cats = [c[0] for c in db.query(Crime.crime_category).distinct().order_by(Crime.crime_category)]
    return {"districts": districts, "crime_types": types, "categories": cats,
            "date_range": {"min": (db.query(func.min(Crime.occurred_at)).scalar() or "")[:10],
                           "max": (db.query(func.max(Crime.occurred_at)).scalar() or "")[:10]},
            "totals": {"crimes": db.query(func.count(Crime.id)).scalar() or 0,
                       "persons": db.query(func.count(Person.id)).scalar() or 0,
                       "vehicles": db.query(func.count(Vehicle.id)).scalar() or 0}}


@api.get("/crimes")
def crimes(db: Session = Depends(get_session), district=None, crime_type=None, category=None,
           date_from=None, date_to=None, q=None, limit: int = 500, offset: int = 0):
    base = _filtered(db, district, crime_type, category, date_from, date_to, q)
    total = base.count()
    rows = base.order_by(Crime.occurred_at.desc()).offset(offset).limit(min(limit, 5000)).all()
    return {"total": total, "items": [r.as_dict() for r in rows]}


@api.get("/stats")
def stats(db: Session = Depends(get_session), district=None, date_from=None, date_to=None):
    rows = _crimes(db, district=district, date_from=date_from, date_to=date_to)
    by_cat, by_dist, by_status, by_month = Counter(), Counter(), Counter(), Counter()
    by_hour = [0] * 24
    for r in rows:
        by_cat[r["crime_category"]] += 1
        by_dist[r["district"]] += 1
        by_status[r["status"]] += 1
        if r["hour"] is not None:
            by_hour[int(r["hour"])] += 1
        by_month[(r["occurred_at"] or "")[:7]] += 1
    total = len(rows)
    solved = sum(by_status.get(s, 0) for s in ("ChargeSheeted", "Closed"))
    return {"kpis": {"total_crimes": total,
                     "open_cases": by_status.get("Open", 0) + by_status.get("UnderInvestigation", 0),
                     "solved_rate": round(100 * solved / total, 1) if total else 0,
                     "districts_affected": len(by_dist),
                     "violent_share": round(100 * by_cat.get("Violent", 0) / total, 1) if total else 0,
                     "cyber_share": round(100 * by_cat.get("Cybercrime", 0) / total, 1) if total else 0},
            "by_category": [{"name": k, "value": v} for k, v in by_cat.most_common()],
            "by_district": [{"name": k, "value": v} for k, v in by_dist.most_common(15)],
            "by_hour": by_hour,
            "by_month": [{"period": k, "count": v} for k, v in sorted(by_month.items()) if k],
            "by_status": [{"name": k, "value": v} for k, v in by_status.items()]}


# ---- spatial intelligence -------------------------------------------------------------------
@api.get("/hotspots")
def hotspots(db: Session = Depends(get_session), resolution: int = 8, crime_type=None,
             date_from=None, date_to=None):
    rows = _crimes(db, crime_type=crime_type, date_from=date_from, date_to=date_to)
    return {"cells": A_hot.compute_hotspots(rows, resolution) if A_hot else []}


@api.get("/emerging")
def emerging(db: Session = Depends(get_session), resolution: int = 8, period_days: int = 90):
    rows = [r.as_dict() for r in db.query(Crime).all()]
    return {"cells": A_hot.emerging_hotspots(rows, resolution, period_days) if A_hot else []}


@api.get("/risk")
def risk(db: Session = Depends(get_session), resolution: int = 8):
    rows = [r.as_dict() for r in db.query(Crime).all()]
    return {"cells": A_risk.risk_scores(rows, resolution) if A_risk else []}


@api.get("/anomalies")
def anomalies(db: Session = Depends(get_session), limit: int = 50):
    rows = [r.as_dict() for r in db.query(Crime).all()]
    return {"items": A_anom.detect_anomalies(rows, limit) if A_anom else []}


@api.get("/timeseries")
def timeseries(db: Session = Depends(get_session), district=None, crime_type=None, interval="month"):
    rows = _crimes(db, district=district, crime_type=crime_type)
    cut = {"day": 10, "week": 10, "month": 7}.get(interval, 7)
    bucket = Counter((r["occurred_at"] or "")[:cut] for r in rows if r["occurred_at"])
    return {"points": [{"period": k, "count": v} for k, v in sorted(bucket.items())]}


# ---- network (Neo4j with SQL fallback) ------------------------------------------------------
def _sql_network(db, fir=None, person=None, depth=1, limit=400):
    if fir:
        firs = {fir}
    elif person:
        firs = {p.fir_number for p in db.query(Person).filter(Person.full_name.like(f"%{person}%")).all()}
    else:
        firs = {c.fir_number for c in db.query(Crime).order_by(Crime.occurred_at.desc()).limit(120).all()}
    seen_firs = set(firs)
    for _ in range(max(0, depth)):
        ids = {p.true_identity_id for p in db.query(Person).filter(Person.fir_number.in_(seen_firs)).all()}
        seen_firs |= {p.fir_number for p in db.query(Person).filter(Person.true_identity_id.in_(ids)).all()}
        if len(seen_firs) > limit:
            break
    seen_firs = set(list(seen_firs)[:limit])
    nodes, edges, seen = [], [], set()

    def add(nid, label, ntype, meta=None):
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "label": label, "type": ntype, "meta": meta or {}})

    for c in db.query(Crime).filter(Crime.fir_number.in_(seen_firs)).all():
        add(f"crime:{c.fir_number}", c.fir_number, "crime", {"type": c.crime_type, "district": c.district})
        add(f"station:{c.police_station}", c.police_station, "station", {"district": c.district})
        edges.append({"source": f"crime:{c.fir_number}", "target": f"station:{c.police_station}", "label": "at"})
    for p in db.query(Person).filter(Person.fir_number.in_(seen_firs)).all():
        pid = f"person:{p.true_identity_id}"
        add(pid, p.full_name, "person", {"role": p.role})
        edges.append({"source": pid, "target": f"crime:{p.fir_number}", "label": p.role})
    for v in db.query(Vehicle).filter(Vehicle.fir_number.in_(seen_firs)).all():
        vid = f"vehicle:{v.reg_number}"
        add(vid, v.reg_number, "vehicle", {"vtype": v.vehicle_type})
        edges.append({"source": vid, "target": f"crime:{v.fir_number}", "label": "linked"})
    return {"nodes": nodes, "edges": edges}


@api.get("/network")
def network(db: Session = Depends(get_session), fir=None, person=None, depth: int = 1, limit: int = 400):
    try:
        return graph_neo4j.network(focus_fir=fir, focus_identity=person, depth=depth, limit=limit)
    except graph_neo4j.GraphUnavailable:
        return _sql_network(db, fir, person, depth, limit)


@api.get("/network/communities")
def communities(db: Session = Depends(get_session)):
    net = _sql_network(db)
    return {"communities": A_comm.detect_communities(net["nodes"], net["edges"]) if A_comm else []}


@api.get("/entity-resolution")
def entity_resolution(db: Session = Depends(get_session), threshold: float = 0.9, limit: int = 300):
    persons = [r.as_dict() for r in db.query(Person).all()]
    pairs = entity_resolution_splink.resolve(persons, threshold)
    return {"total": len(pairs), "pairs": pairs[:limit]}


@api.get("/mo-linkage")
def mo_linkage(db: Session = Depends(get_session), fir: str = Query(...), top_k: int = 10):
    target = db.query(Crime).filter(Crime.fir_number == fir).first()
    if not target:
        return {"target": fir, "matches": []}
    rows = [r.as_dict() for r in db.query(Crime).filter(Crime.crime_category == target.crime_category).all()]
    return {"target": fir, "matches": A_mo.link_by_mo(target.as_dict(), rows, top_k) if A_mo else []}


# ---- assistant (vector RAG) -----------------------------------------------------------------
@api.post("/assistant/chat")
def chat(payload: dict, db: Session = Depends(get_session)):
    msg = (payload or {}).get("message", "")
    fallback = [r.as_dict() for r in db.query(Crime).order_by(Crime.occurred_at.desc()).limit(1500).all()]
    return vector_rag.answer(msg, fallback)


# ---- cyber / CDR / missing / patrol ---------------------------------------------------------
@api.get("/cyber/overview")
def cyber_overview(db: Session = Depends(get_session)):
    crimes_ = [r.as_dict() for r in db.query(Crime).filter(Crime.crime_category == "Cybercrime").all()]
    return A_cyber.cyber_overview(crimes_) if A_cyber else {"kpis": {"total": len(crimes_)}}


@api.get("/cyber/mules")
def cyber_mules(db: Session = Depends(get_session), limit: int = 50):
    if not A_cyber:
        return {"total": 0, "items": []}
    items = A_cyber.detect_mules([r.as_dict() for r in db.query(Account).all()],
                                 [r.as_dict() for r in db.query(Transaction).all()], limit)
    return {"total": len(items), "items": items}


@api.get("/cyber/money-flow")
def cyber_money_flow(db: Session = Depends(get_session), account: str = Query(...), depth: int = 2):
    if not A_cyber:
        return {"nodes": [], "edges": []}
    return A_cyber.money_flow([r.as_dict() for r in db.query(Transaction).all()],
                              [r.as_dict() for r in db.query(Account).all()], account, depth)


@api.get("/cdr/contacts")
def cdr_contacts(db: Session = Depends(get_session), msisdn: str = Query(...)):
    return A_cdr.cdr_contacts(_cdr_rows(db), msisdn) if A_cdr else {"msisdn": msisdn, "top_contacts": []}


@api.get("/cdr/network")
def cdr_network(db: Session = Depends(get_session), msisdn: str = Query(...), depth: int = 1):
    return A_cdr.cdr_network(_cdr_rows(db), msisdn, depth) if A_cdr else {"nodes": [], "edges": []}


@api.get("/cdr/tower-dump")
def cdr_tower_dump(db: Session = Depends(get_session), tower: str = Query(...), start=None, end=None):
    return A_cdr.tower_dump(_cdr_rows(db), tower, start, end) if A_cdr else {"tower": tower, "numbers": []}


@api.get("/missing/cases")
def missing_cases(db: Session = Depends(get_session), status: str = None, risk: str = None):
    q = db.query(MissingPerson)
    if status:
        q = q.filter(MissingPerson.status == status)
    if risk:
        q = q.filter(MissingPerson.risk_tier == risk)
    return {"items": [r.as_dict() for r in q.all()]}


@api.get("/patrol/optimize")
def patrol_optimize(db: Session = Depends(get_session), resolution: int = 8, units: int = 15):
    rows = [r.as_dict() for r in db.query(Crime).all()]
    return A_patrol.optimize_patrol(rows, resolution, units) if A_patrol else {"assignments": []}


@api.get("/nlp/extract")
def nlp_extract(db: Session = Depends(get_session), fir: str = Query(...)):
    c = db.query(Crime).filter(Crime.fir_number == fir).first()
    if not c:
        return {"fir": fir, "entities": {}, "keywords": [], "summary": "FIR not found."}
    return {"fir": fir, **(A_nlp.extract_entities(c.as_dict()) if A_nlp else {"entities": {}, "keywords": []})}


@api.get("/briefing")
def briefing(db: Session = Depends(get_session), district: str = None):
    s = stats(db, district=district)
    hs = hotspots(db).get("cells", [])[:20]
    em = emerging(db).get("cells", [])
    an = anomalies(db, limit=10).get("items", [])
    return A_brief.generate_briefing(s, hs, em, an, district) if A_brief else {"sections": []}


# ---- oversight ------------------------------------------------------------------------------
@api.get("/oversight/fairness")
def oversight_fairness(db: Session = Depends(get_session)):
    rows = [r.as_dict() for r in db.query(Crime).all()]
    return A_over.fairness_metrics(rows) if A_over else {"coverage_by_district": []}


@api.get("/oversight/audit")
def oversight_audit(db: Session = Depends(get_session), limit: int = 50):
    integrity = audit.verify_chain(db)
    rows = db.query(AuditLog).order_by(AuditLog.seq.desc()).limit(limit).all()
    return {"entries": [{"seq": r.seq, "ts": r.ts.isoformat() if r.ts else None, "user": r.user,
                         "action": r.action, "resource": r.resource, "entry_hash": r.entry_hash}
                        for r in rows], "integrity": integrity}


# ---- admin (RBAC: admin only) ---------------------------------------------------------------
admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_role("admin"))])


@admin.get("/audit/verify")
def audit_verify(db: Session = Depends(get_session)):
    return audit.verify_chain(db)


@admin.post("/crypto-shred")
def crypto_shred(record_ref: str = Query(...), db: Session = Depends(get_session)):
    return encryption.crypto_shred(db, record_ref)
