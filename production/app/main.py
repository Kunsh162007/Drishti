"""Production entrypoint. Wires auth, rate limiting, security headers, the audit
ledger, and serves the SAME frontend as the demo. Run from `production/`:

    uvicorn app.main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .db import create_all, SessionLocal
from .api import public, api, admin
from .security import auth
from .security.ratelimit import RateLimitMiddleware
from .models import User

app = FastAPI(title=settings.APP_TITLE, version=settings.APP_VERSION)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list or ["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(RateLimitMiddleware)


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp


app.add_middleware(SecurityHeaders)


def _seed_admin():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == settings.ADMIN_USERNAME).first():
            db.add(User(username=settings.ADMIN_USERNAME,
                        hashed_password=auth.hash_password(settings.ADMIN_PASSWORD),
                        role="admin", full_name=settings.ADMIN_FULL_NAME, is_active=True))
            db.commit()
    finally:
        db.close()


@app.on_event("startup")
def _startup():
    create_all()
    _seed_admin()


app.include_router(public)
app.include_router(api)
app.include_router(admin)

# Serve the same frontend as the demo (behind your SSO / auth proxy in production).
_FRONTEND = Path(__file__).resolve().parents[2] / "demo" / "frontend"
if _FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
