"""DRISHTI demo entrypoint: FastAPI app serving the API (/api) and the static frontend (/)."""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from . import config
from .db import Base, engine
from .api import router as api_router

app = FastAPI(title=config.APP_TITLE, version=config.APP_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Create tables if they don't exist (no-op when the seeded SQLite file is present).
Base.metadata.create_all(bind=engine)

app.include_router(api_router)


@app.middleware("http")
async def audit_middleware(request, call_next):
    """Log every sensitive API call into the tamper-evident ledger (demo: single 'officer')."""
    response = await call_next(request)
    try:
        path = request.url.path
        if (path.startswith("/api/") and path != "/api/health"
                and not path.startswith("/api/oversight/audit")):
            from .db import SessionLocal
            from . import audit as audit_mod
            db = SessionLocal()
            try:
                audit_mod.append(db, user="demo-officer", action=request.method,
                                 resource=path, detail=str(dict(request.query_params))[:180])
            finally:
                db.close()
    except Exception:
        pass
    return response


@app.get("/api")
def api_root():
    return {"name": config.APP_TITLE, "version": config.APP_VERSION, "mode": config.MODE,
            "docs": "/docs", "endpoints": "/api/health, /api/meta, /api/hotspots, /api/network, ..."}


# Serve the frontend last so it doesn't shadow /api routes.
if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/")
    def _placeholder():
        return JSONResponse({"message": "Frontend not built yet. API is live at /api/health."})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
