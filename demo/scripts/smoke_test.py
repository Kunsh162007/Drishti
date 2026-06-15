"""End-to-end smoke test: boots the FastAPI app in-process and exercises every endpoint."""
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1]  # demo/
sys.path.insert(0, str(DEMO))

from fastapi.testclient import TestClient  # noqa: E402
from backend.main import app  # noqa: E402

c = TestClient(app)
ok = 0
fail = 0


def check(name, resp, validate=None):
    global ok, fail
    try:
        assert resp.status_code == 200, f"HTTP {resp.status_code}"
        data = resp.json()
        info = validate(data) if validate else ""
        print(f"  [OK] {name:32} {info}")
        ok += 1
    except Exception as e:
        print(f"  [FAIL] {name:32} {e}  body={getattr(resp,'text','')[:160]}")
        fail += 1


print("=== DRISHTI API smoke test ===")
check("GET /api/health", c.get("/api/health"), lambda d: f"records={d['records']} mode={d['mode']}")
meta = c.get("/api/meta")
check("GET /api/meta", meta, lambda d: f"{len(d['districts'])} districts, {len(d['crime_types'])} types, range {d['date_range']['min']}..{d['date_range']['max']}")
md = meta.json()
sample_type = md["crime_types"][0]
sample_dist = md["districts"][0]

check("GET /api/crimes", c.get("/api/crimes", params={"limit": 50}), lambda d: f"total={d['total']} returned={len(d['items'])}")
check("GET /api/stats", c.get("/api/stats"), lambda d: f"total={d['kpis']['total_crimes']} solved%={d['kpis']['solved_rate']} cats={len(d['by_category'])}")
check("GET /api/hotspots r8", c.get("/api/hotspots", params={"resolution": 8}), lambda d: f"{len(d['cells'])} cells, top count={d['cells'][0]['count'] if d['cells'] else 0}, hot={sum(1 for x in d['cells'] if x['level']=='hot')}")
check("GET /api/emerging", c.get("/api/emerging", params={"resolution": 8, "period_days": 120}), lambda d: f"{len(d['cells'])} emerging; new={sum(1 for x in d['cells'] if x['category']=='new')}")
check("GET /api/risk", c.get("/api/risk", params={"resolution": 8}), lambda d: f"{len(d['cells'])} risk cells, max={d['cells'][0]['risk'] if d['cells'] else 0}")
check("GET /api/anomalies", c.get("/api/anomalies", params={"limit": 20}), lambda d: f"{len(d['items'])} anomalies")
check("GET /api/timeseries", c.get("/api/timeseries", params={"interval": "month"}), lambda d: f"{len(d['points'])} points")
check("GET /api/network", c.get("/api/network"), lambda d: f"{len(d['nodes'])} nodes, {len(d['edges'])} edges")
check("GET /api/network/communities", c.get("/api/network/communities"), lambda d: f"{len(d['communities'])} communities")
check("GET /api/entity-resolution", c.get("/api/entity-resolution", params={"threshold": 0.82}), lambda d: f"{len(d['pairs'])} duplicate pairs; auto={sum(1 for p in d['pairs'] if p['decision']=='auto')}")

# MO linkage needs a FIR
fir = c.get("/api/crimes", params={"limit": 1}).json()["items"][0]["fir_number"]
check("GET /api/mo-linkage", c.get("/api/mo-linkage", params={"fir": fir, "top_k": 8}), lambda d: f"target={d['target']} matches={len(d['matches'])}")
check("POST /api/assistant/chat", c.post("/api/assistant/chat", json={"message": f"vehicle thefts in {sample_dist} last month", "session_id": "t1"}), lambda d: f"mode={d['mode']} citations={len(d['citations'])} grounded={d['grounded']}")
check("POST /api/assistant (no data)", c.post("/api/assistant/chat", json={"message": "crimes on the moon in 1850", "session_id": "t2"}), lambda d: f"mode={d['mode']} (should refuse) cites={len(d['citations'])}")

# MyShield: pick a real person with a phone
ppl = c.get("/api/crimes", params={"limit": 1}).json()
check("GET /api/myshield", c.get("/api/myshield", params={"identifier": fir, "token": "demo"}), lambda d: f"matches={len(d['matches'])} area={'yes' if d['area_safety'] else 'no'}")

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
