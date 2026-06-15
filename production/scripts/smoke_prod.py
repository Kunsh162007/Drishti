"""Production boot + auth smoke test (uses whatever DATABASE_URL points to)."""
import sys
from pathlib import Path

PROD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.config import settings  # noqa: E402

ok = fail = 0


def check(name, cond, info=""):
    global ok, fail
    if cond:
        print(f"  [OK] {name:30} {info}"); ok += 1
    else:
        print(f"  [FAIL] {name:30} {info}"); fail += 1


with TestClient(app) as c:
    h = c.get("/health")
    check("health", h.status_code == 200, f"records={h.json().get('records')}")
    # protected endpoint must reject without a token
    check("auth enforced (401)", c.get("/api/hotspots").status_code == 401)
    # login
    r = c.post("/auth/login", data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD})
    check("login", r.status_code == 200, f"role={r.json().get('role')}")
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    check("hotspots (authed)", c.get("/api/hotspots", headers=H).status_code == 200)
    check("network (neo4j->sql fallback)", c.get("/api/network", headers=H).status_code == 200)
    er = c.get("/api/entity-resolution", headers=H)
    check("entity-res (splink->fallback)", er.status_code == 200, f"pairs={er.json().get('total')}")
    asst = c.post("/api/assistant/chat", json={"message": "vehicle theft in Bengaluru"}, headers=H)
    check("assistant (rag fallback)", asst.status_code == 200, f"mode={asst.json().get('mode')}")
    check("cyber/mules", c.get("/api/cyber/mules", headers=H).status_code == 200)
    aud = c.get("/api/oversight/audit", headers=H)
    check("audit ledger valid", aud.json()["integrity"]["valid"] is True, f"count={aud.json()['integrity']['count']}")
    check("admin verify (RBAC)", c.get("/api/admin/audit/verify", headers=H).status_code == 200)
    shred = c.post("/api/admin/crypto-shred", params={"record_ref": "person:demo"}, headers=H)
    check("admin crypto-shred", shred.status_code == 200, str(shred.json().get("shredded")))

print(f"\nRESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
