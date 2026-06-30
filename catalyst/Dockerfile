# ============================================================================
# DRISHTI — Catalyst AppSail image (custom OCI runtime)
# ----------------------------------------------------------------------------
# AppSail runs this container and injects the listen port via the env var
# X_ZOHO_CATALYST_LISTEN_PORT (default 9000). The app must bind 0.0.0.0:$PORT.
#
# Build context = REPOSITORY ROOT (this image needs the demo/ folder):
#   docker build -f catalyst/Dockerfile -t drishti-appsail .
# Locally:
#   docker run -p 9000:9000 -e X_ZOHO_CATALYST_LISTEN_PORT=9000 drishti-appsail
# ============================================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DRISHTI_MODE=demo \
    LLM_PROVIDER=none \
    X_ZOHO_CATALYST_LISTEN_PORT=9000

WORKDIR /srv

# Bundled SQLite demo needs no system DB client; build-essential covers sci wheels.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY demo/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

# Ship the demo (code + frontend + seeded drishti_demo.db + KSP schema/ETL).
COPY demo /srv/demo
WORKDIR /srv/demo

EXPOSE 9000
# Robust entrypoint: binds the AppSail port (X_ZOHO_CATALYST_LISTEN_PORT, default
# 9000) and makes the bundled SQLite DB writable. `python` exists in python:slim.
CMD ["python", "appsail_run.py"]
