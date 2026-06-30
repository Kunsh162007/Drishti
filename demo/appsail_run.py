"""
AppSail entrypoint for DRISHTI (Catalyst managed Python runtime).

Why this exists:
  • AppSail runs the start command DIRECTLY (no shell), so `$X_ZOHO_CATALYST_LISTEN_PORT`
    in a command line would not expand — we read it here in Python instead.
  • The AppSail app directory can be read-only at runtime, which would break the
    bundled SQLite DB (WAL writes + the audit ledger). So we copy the seeded DB to
    writable /tmp and point the app there via DATABASE_URL before the app imports.

Start command (app-config.json):  python appsail_run.py
"""
import os
import shutil
from pathlib import Path

# 1) Make the seeded SQLite DB writable: copy it to /tmp and point the app at it.
_src = Path(__file__).resolve().parent / "data" / "drishti_demo.db"
_dst = Path(os.getenv("TMPDIR", "/tmp")) / "drishti_demo.db"
try:
    if _src.exists() and not _dst.exists():
        _dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_src, _dst)
    if _dst.exists():
        os.environ.setdefault("DATABASE_URL", f"sqlite:///{_dst.as_posix()}")
except Exception as e:  # fall back to the bundled (possibly read-only) DB
    print(f"[appsail_run] DB copy skipped: {e}")

# 2) Start the API + frontend on the port Catalyst assigns (default 9000).
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("X_ZOHO_CATALYST_LISTEN_PORT", "9000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)
