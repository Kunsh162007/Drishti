# ============================================================================
# DRISHTI demo — container image
# ----------------------------------------------------------------------------
# Clean python:3.12-slim image that installs deps, generates + seeds the
# bundled SQLite data at build time, and starts uvicorn.
#
# IMPORTANT module-path detail:
#   The data scripts compute ROOT as TWO levels above their own file
#   (i.e. the repo root) and import `demo.backend.*`. So inside the container
#   we mirror that layout: the application lives at /app/demo/** and the build
#   context is the `demo/` folder itself. We therefore COPY the demo folder to
#   /app/demo and run the scripts from /app so `demo.backend` resolves, while
#   uvicorn is launched from /app/demo so `backend.main:app` resolves.
#
# Build (from inside the demo/ folder):
#   docker build -t drishti-demo .
# Run:
#   docker run --rm -p 8000:8000 drishti-demo
#   # then open http://localhost:8000
# ============================================================================
FROM python:3.12-slim

# Faster, cleaner Python in containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    DRISHTI_MODE=demo \
    LLM_PROVIDER=none

WORKDIR /app

# --- dependencies (cached layer) -------------------------------------------
# The build context is the demo/ folder, so requirements.txt is at the root.
COPY requirements.txt /app/demo/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/demo/requirements.txt

# --- application + seed CSVs ------------------------------------------------
# Copy the whole demo folder into /app/demo to match the demo.backend.* layout.
COPY . /app/demo

# --- generate + seed the bundled SQLite DB at build time --------------------
# Run from /app so the scripts' `demo.backend` imports resolve. The scripts are
# CWD-independent (they self-insert the repo root onto sys.path), but running
# from /app keeps everything explicit. The DB lands at /app/demo/data/.
RUN python demo/scripts/generate_data.py && python demo/scripts/seed_db.py

EXPOSE 8000

# uvicorn must run from inside demo/ so that `backend.main:app` is importable.
WORKDIR /app/demo
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
