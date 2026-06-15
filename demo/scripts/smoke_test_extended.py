"""Smoke test for the EXTENDED features (NLP, CDR, cyber, missing, patrol, oversight, briefing)."""
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO))

from fastapi.testclient import TestClient  # noqa: E402
from backend.main import app  # noqa: E402

c = TestClient(app)
ok = fail = 0


def check(name, resp, validate=None):
    global ok, fail
    try:
        assert resp.status_code == 200, f"HTTP {resp.status_code}"
        data = resp.json()
        info = validate(data) if validate else ""
        print(f"  [OK] {name:34} {info}")
        ok += 1
    except Exception as e:
        print(f"  [FAIL] {name:34} {e}  body={getattr(resp,'text','')[:160]}")
        fail += 1


print("=== DRISHTI extended-features smoke test ===")
fir = c.get("/api/crimes", params={"limit": 1}).json()["items"][0]["fir_number"]
cyber_fir = c.get("/api/crimes", params={"category": "Cybercrime", "limit": 1}).json()["items"]
cyber_fir = cyber_fir[0]["fir_number"] if cyber_fir else fir
samp = c.get("/api/cdr/sample").json()
msisdn, tower = samp.get("msisdn"), samp.get("tower")
acct = c.get("/api/cyber/sample").json().get("account")

check("GET /api/nlp/extract", c.get("/api/nlp/extract", params={"fir": cyber_fir}),
      lambda d: f"entities={ {k:len(v) for k,v in (d.get('entities') or {}).items()} } kw={len(d.get('keywords',[]))}")
check("GET /api/cdr/contacts", c.get("/api/cdr/contacts", params={"msisdn": msisdn}),
      lambda d: f"calls={d.get('total_calls')} contacts={len(d.get('top_contacts',[]))} colo={len(d.get('co_location',[]))}")
check("GET /api/cdr/network", c.get("/api/cdr/network", params={"msisdn": msisdn, "depth": 1}),
      lambda d: f"nodes={len(d['nodes'])} edges={len(d['edges'])}")
check("GET /api/cdr/tower-dump", c.get("/api/cdr/tower-dump", params={"tower": tower}),
      lambda d: f"numbers={len(d.get('numbers',[]))}")
check("GET /api/cyber/overview", c.get("/api/cyber/overview"),
      lambda d: f"total={d['kpis'].get('total')} types={len(d.get('by_type',[]))} trend={len(d.get('trend',[]))}")
check("GET /api/cyber/mules", c.get("/api/cyber/mules", params={"limit": 30}),
      lambda d: f"total={d['total']} top_score={d['items'][0]['score'] if d['items'] else 0}")
check("GET /api/cyber/money-flow", c.get("/api/cyber/money-flow", params={"account": acct, "depth": 2}),
      lambda d: f"nodes={len(d['nodes'])} edges={len(d['edges'])}")
check("GET /api/missing/cases", c.get("/api/missing/cases"),
      lambda d: f"cases={len(d['items'])} high={sum(1 for x in d['items'] if x['risk_tier']=='High')}")
check("GET /api/patrol/optimize", c.get("/api/patrol/optimize", params={"units": 15}),
      lambda d: f"assignments={len(d['assignments'])} coverage={d.get('coverage_pct')}%")
check("GET /api/oversight/fairness", c.get("/api/oversight/fairness"),
      lambda d: f"districts={len(d['coverage_by_district'])} flags={len(d['disparity_flags'])}")
check("GET /api/briefing", c.get("/api/briefing"),
      lambda d: f"sections={len(d['sections'])} headline='{(d.get('headline') or '')[:40]}'")
# audit ledger should now contain entries from all the calls above; chain must verify
check("GET /api/oversight/audit", c.get("/api/oversight/audit", params={"limit": 100}),
      lambda d: f"entries={len(d['entries'])} chain_valid={d['integrity']['valid']} count={d['integrity']['count']}")

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
