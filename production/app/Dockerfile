# DRISHTI production image. Build context = repo root (needs demo/ for shared analytics + frontend).
#   docker build -f production/app/Dockerfile -t drishti-prod .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv

# System deps for psycopg / scientific wheels
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY production/app/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

# Bring in the production app AND the shared demo package (analytics + frontend)
COPY production /srv/production
COPY demo /srv/demo

WORKDIR /srv/production
EXPOSE 8080
# DATABASE_URL, JWT_SECRET, MASTER_ENCRYPTION_KEY, LLM_* etc. are injected at runtime.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
