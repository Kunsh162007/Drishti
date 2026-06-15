"""End-to-end feature test against a running DRISHTI (demo OR production).

Usage:
    python demo/scripts/test_live.py                         # tests the live demo
    python demo/scripts/test_live.py http://localhost:8000   # tests a local demo
    python demo/scripts/test_live.py https://your-prod-host admin "<password>"  # production

It logs in, wakes the server if it's cold, then exercises every feature endpoint
and prints PASS/FAIL with a one-line data summary for each.
"""
import sys
import time
import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://drishti-demo.onrender.com").rstrip("/")
USER = sys.argv[2] if len(sys.argv) > 2 else "officer"
PASS = sys.argv[3] if len(sys.argv) > 3 else "drishti"

c = httpx.Client(timeout=90, follow_redirects=True)
ok = fail = 0


def check(name, cond, info=""):
    global ok, fail
    flag = "OK " if cond else "FAIL"
    print(f"  [{flag}] {name:30} {info}")
    ok += 1 if cond else 0
    fail += 0 if cond else 1


def get(path, **params):
    return c.get(BASE + path, params=params)


print(f"\n=== DRISHTI live feature test : {BASE} ===")

# 0) wake the server (free tier can cold-start ~50s)
for i in range(10):
    try:
        if c.get(BASE + "/api/health").status_code == 200:
            break
    except Exception:
        pass
    print(f"  waking server... ({i+1})"); time.sleep(8)

# 1) auth
r = c.post(BASE + "/api/auth/login", data={"username": USER, "password": PASS})
check("login", r.status_code == 200, f"role={r.json().get('role') if r.status_code==200 else r.text[:50]}")
if r.status_code == 200:
    c.headers["Authorization"] = "Bearer " + r.json()["access_token"]

# 2) overview
h = get("/api/health").json()
check("health", h.get("records", 0) > 0, f"records={h.get('records')} mode={h.get('mode') or h.get('env')}")
m = get("/api/meta").json()
check("meta", len(m.get("districts", [])) > 0, f"{len(m['districts'])} districts, {len(m['crime_types'])} crime types")
s = get("/api/stats").json()
check("stats / dashboard", s.get("kpis", {}).get("total_crimes", 0) > 0,
      f"total={s['kpis']['total_crimes']} solved={s['kpis']['solved_rate']}%")

# 3) geospatial
hot = get("/api/hotspots", resolution=8).json()
check("hotspots", len(hot.get("cells", [])) > 0, f"{len(hot['cells'])} cells, hot={sum(1 for x in hot['cells'] if x['level']=='hot')}")
em = get("/api/emerging", resolution=8, period_days=120).json()
check("emerging trends", "cells" in em, f"{len(em.get('cells', []))} emerging cells")
rk = get("/api/risk", resolution=8).json()
check("risk (place-based)", len(rk.get("cells", [])) > 0, f"{len(rk['cells'])} risk cells")
an = get("/api/anomalies", limit=20).json()
check("anomalies", "items" in an, f"{len(an.get('items', []))} flagged")

# 4) network / investigations
net = get("/api/network").json()
check("network graph", len(net.get("nodes", [])) > 0, f"{len(net['nodes'])} nodes / {len(net['edges'])} edges")
comm = get("/api/network/communities").json()
check("communities", "communities" in comm, f"{len(comm.get('communities', []))} communities")
er = get("/api/entity-resolution", threshold=0.82).json()
check("entity resolution", er.get("total", 0) > 0, f"{er.get('total')} duplicate pairs")
fir = get("/api/crimes", limit=1).json()["items"][0]["fir_number"]
mo = get("/api/mo-linkage", fir=fir, top_k=8).json()
check("MO linkage", "matches" in mo, f"target={fir} matches={len(mo.get('matches', []))}")
nlp = get("/api/nlp/extract", fir=fir).json()
check("NLP extraction", "entities" in nlp, f"keywords={len(nlp.get('keywords', []))}")

# 5) assistant
asst = c.post(BASE + "/api/assistant/chat", json={"message": "vehicle theft in Bengaluru last month"}).json()
check("assistant (grounded)", asst.get("grounded") is True, f"mode={asst.get('mode')} citations={len(asst.get('citations', []))}")

# 6) cyber / CDR
cy = get("/api/cyber/overview").json()
check("cyber overview", "kpis" in cy, f"cyber FIRs={cy.get('kpis', {}).get('total')}")
mul = get("/api/cyber/mules", limit=30).json()
check("mule detection", mul.get("total", 0) > 0, f"{mul.get('total')} flagged accounts")
acct = get("/api/cyber/sample").json().get("account")
mf = get("/api/cyber/money-flow", account=acct, depth=2).json()
check("money-flow graph", "nodes" in mf, f"{len(mf.get('nodes', []))} accounts traced")
samp = get("/api/cdr/sample").json()
cdrc = get("/api/cdr/contacts", msisdn=samp.get("msisdn")).json()
check("CDR contacts", cdrc.get("total_calls", 0) > 0, f"calls={cdrc.get('total_calls')} co-location={len(cdrc.get('co_location', []))}")
td = get("/api/cdr/tower-dump", tower=samp.get("tower")).json()
check("CDR tower-dump", "numbers" in td, f"{len(td.get('numbers', []))} numbers at tower")

# 7) preventive / oversight
mp = get("/api/missing/cases").json()
check("missing persons", len(mp.get("items", [])) > 0, f"{len(mp['items'])} cases")
pt = get("/api/patrol/optimize", units=15).json()
check("patrol optimisation", len(pt.get("assignments", [])) > 0, f"{len(pt['assignments'])} assignments, coverage={pt.get('coverage_pct')}%")
fr = get("/api/oversight/fairness").json()
check("oversight fairness", "coverage_by_district" in fr, f"{len(fr.get('coverage_by_district', []))} districts")
au = get("/api/oversight/audit", limit=50).json()
check("audit ledger (tamper-evident)", au.get("integrity", {}).get("valid") is True,
      f"chain_valid={au.get('integrity', {}).get('valid')} entries={au.get('integrity', {}).get('count')}")
br = get("/api/briefing").json()
check("auto briefing", len(br.get("sections", [])) > 0, f"{len(br.get('sections', []))} sections")

print(f"\n=== RESULT: {ok} passed, {fail} failed ===")
sys.exit(1 if fail else 0)
