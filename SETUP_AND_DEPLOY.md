# DRISHTI — Setup, API Keys & Deployment Guide

This guide tells you **exactly what you must provide** (database connection, API keys,
hosting) and **how to deploy** both the free **demo** and the full **production** app.

> **What is already done for you:** 100% of the application code (backend, analytics,
> frontend, security, audit ledger, encryption, services) for *both* the demo and the
> production product is written and tested. **The only things intentionally left blank**
> are: (1) the production **database connection string**, (2) **API keys / secrets**, and
> (3) the **deployment** itself. Everything below is filling those three in.

---

## Part 1 — Run the DEMO locally (no keys, 100% free)

Nothing to obtain. From the repo root (Windows PowerShell):

```powershell
cd "demo"
python -m pip install -r requirements.txt
python ..\demo\scripts\generate_data.py        # (already generated; safe to re-run)
python ..\demo\scripts\generate_extended_data.py
python ..\demo\scripts\seed_db.py              # builds the SQLite DB with seed data
python -m uvicorn backend.main:app --port 8000
```

Open **http://localhost:8000**. That's the whole platform — maps, network, CDR, cyber,
predictive, investigations, assistant, MyShield, oversight, patrol, missing persons.

To verify: `python scripts/smoke_test.py` and `python scripts/smoke_test_extended.py`.

---

## Part 2 — Deploy the DEMO free on Render

**Accounts needed (all free):** a GitHub account, a Render account. **No API keys.**

1. Push this repo to GitHub.
2. Render → **New ▸ Blueprint** → connect the repo → it auto-detects `demo/render.yaml`.
3. Click **Apply**. Render installs deps, generates + seeds data, and starts the app.
4. Your demo is live at `https://<your-app>.onrender.com`.
   - Free tier sleeps after ~15 min idle; first hit takes ~50s to wake. That's normal.

Optional: to enable a *real* LLM in the demo (instead of the free grounded/extractive
assistant), add env vars in the Render dashboard — see the keys table in Part 4.

---

## Part 3 — API keys & accounts checklist

| # | What | Needed for | Free? | Where to get it | Env variable(s) |
|---|------|-----------|-------|-----------------|-----------------|
| 1 | **Nothing** | The demo as-is | ✅ Free | — | — |
| 2 | **GitHub + Render account** | Deploying the demo | ✅ Free | github.com, render.com | — |
| 3 | **JWT secret** | Production login/auth | ✅ Free (you generate) | `python -c "import secrets;print(secrets.token_urlsafe(48))"` | `JWT_SECRET` |
| 4 | **Fernet master key** | Production field encryption / crypto-shred | ✅ Free (you generate) | `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` | `MASTER_ENCRYPTION_KEY` |
| 5 | **Postgres database** | Production data store | 💰 Paid (managed) or self-host | Render/Neon/AWS RDS, or the bundled compose `db` | `DATABASE_URL`, `POSTGRES_*` |
| 6 | **Admin password** | First production login | ✅ Free (you choose) | — | `ADMIN_PASSWORD` |
| 7 | **Claude API key** *(optional)* | Generative assistant (best quality) | 💰 Paid | console.anthropic.com | `LLM_PROVIDER=anthropic`, `LLM_API_KEY`, `LLM_MODEL=claude-opus-4-8` |
| 7b | **Groq API key** *(optional, alt)* | Generative assistant on free-tier Llama | ✅ Free tier | console.groq.com | `LLM_PROVIDER=groq`, `LLM_API_KEY`, `LLM_MODEL=llama-3.3-70b-versatile` |
| 8 | **Neo4j** *(optional)* | Graph DB for networks (else SQL fallback) | ✅ Self-host / 💰 Aura | neo4j.com / compose `neo4j` | `NEO4J_URI/USER/PASSWORD` |
| 9 | **Qdrant** *(optional)* | Vector RAG for assistant (else keyword fallback) | ✅ Self-host / 💰 cloud | qdrant.tech / compose `qdrant` | `QDRANT_URL` |

**Minimum to run production:** items 3, 4, 5, 6. Items 7–9 are optional — the app runs
without them (the assistant uses free grounded retrieval; graph uses SQL; RAG uses keywords).

---

## Part 4 — Deploy the PRODUCTION product (Docker Compose)

The production app is the **same features** as the demo with Postgres, JWT auth, RBAC,
a tamper-evident audit ledger, field encryption + crypto-shred, rate limiting, and
optional Neo4j/Qdrant/Claude — all toggled by environment variables.

### Step 1 — Generate your secrets
```bash
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print('MASTER_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

### Step 2 — Fill the env file
```bash
cd production
cp .env.production.example .env.production
# edit .env.production: paste the two secrets above, set POSTGRES_PASSWORD,
# DATABASE_URL, ADMIN_PASSWORD. Leave LLM_PROVIDER=none unless you have a key.
```

### Step 3 — Launch the stack
```bash
docker compose --env-file .env.production up -d --build
```
This starts: the app, **PostgreSQL/PostGIS**, **Neo4j**, **Qdrant**, and a **Caddy**
reverse proxy (TLS). (You can comment out neo4j/qdrant in `docker-compose.yml` if not used.)

### Step 4 — Seed the database (first time only)
```bash
docker compose exec app python scripts/seed_prod.py
```

### Step 5 — Log in
- Open your domain (or `http://localhost`).
- Get a token: `POST /auth/login` with `username=admin` and your `ADMIN_PASSWORD`.
- The SPA is served at `/`; put it behind your **SSO / auth proxy** (recommended for
  government), or have the front-end call `/auth/login` and send the bearer token.

### Step 6 — Verify it's healthy
```bash
docker compose exec app python scripts/smoke_prod.py   # 11 checks incl. auth + audit chain
```

### Optional toggles (just edit `.env.production` and restart)
- **Real assistant:** set `LLM_PROVIDER=anthropic`, `LLM_API_KEY=sk-ant-...`, `LLM_MODEL=claude-opus-4-8` (or the Groq trio).
- **Graph DB:** ensure `NEO4J_*` point at a running Neo4j (with the APOC plugin). Then `docker compose exec app python -c "..."` to sync, or it falls back to SQL automatically.
- **Vector RAG:** ensure `QDRANT_URL` is reachable, then index FIRs once via `vector_rag.index_firs(...)`. Falls back to keyword retrieval otherwise.

### Sovereign / GovCloud notes
- Host on **NIC MeghRaj / on-prem**; inject `JWT_SECRET`, `MASTER_ENCRYPTION_KEY`, DB and
  LLM secrets from an **HSM/KMS** at runtime rather than a file.
- Keep `LLM_PROVIDER` on a **self-hosted Llama gateway** for sensitive data; reserve Claude
  for redacted/aggregate workloads (per the proposal's data-sovereignty design).
- The audit ledger (`/api/oversight/audit`, `/api/admin/audit/verify`) gives you the
  tamper-evidence; `MASTER_ENCRYPTION_KEY` + `/api/admin/crypto-shred` give crypto-erase.

---

## What costs money vs. what's free

- **Free forever:** the entire demo, all source code, the production app code, the
  grounded assistant (no LLM key), SQL graph fallback, keyword RAG fallback, self-hosted
  Postgres/Neo4j/Qdrant via Docker.
- **Costs money only if you choose:** managed Postgres hosting, a Claude API key (Groq has
  a free tier), cloud Neo4j/Qdrant, GPUs for a self-hosted LLM, and server/hosting + HSM
  for a real sovereign deployment.
