#!/usr/bin/env bash
# ============================================================================
# DRISHTI demo — convenience local runner.
# Creates a venv (if missing), installs deps, generates + seeds the SQLite DB
# (only if it doesn't already exist), then starts uvicorn.
#
# Usage (from inside the demo/ folder, on macOS/Linux/Git-Bash):
#   ./start.sh
#   PORT=9000 ./start.sh          # custom port
#   RESEED=1 ./start.sh           # force regenerate + reseed the DB
#
# On native Windows PowerShell, use the commands in README.md instead.
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")"                    # always run from the demo/ folder
PORT="${PORT:-8000}"

# --- venv -------------------------------------------------------------------
if [ ! -d ".venv" ]; then
  echo "[start] creating virtualenv (.venv)..."
  python -m venv .venv
fi
# shellcheck disable=SC1091
if [ -f ".venv/Scripts/activate" ]; then
  source .venv/Scripts/activate        # Windows (Git-Bash) layout
else
  source .venv/bin/activate            # POSIX layout
fi

# --- deps -------------------------------------------------------------------
echo "[start] installing dependencies..."
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# --- data + DB --------------------------------------------------------------
# The scripts derive paths from __file__ and self-insert the repo root, so they
# work from here. The DB always lands at demo/data/drishti_demo.db.
if [ "${RESEED:-0}" = "1" ] || [ ! -f "data/drishti_demo.db" ]; then
  echo "[start] generating synthetic data + seeding SQLite DB..."
  python scripts/generate_data.py
  python scripts/seed_db.py
else
  echo "[start] data/drishti_demo.db already exists — skipping seed (RESEED=1 to force)."
fi

# --- serve ------------------------------------------------------------------
echo "[start] launching DRISHTI at http://localhost:${PORT}  (Ctrl+C to stop)"
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}" --reload
