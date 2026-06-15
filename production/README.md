<div align="center">

# 🏭 DRISHTI — Production Architecture

*Same application code as the demo. Different infrastructure, full power, sovereign posture.*

</div>

---

## The core idea

The free demo (`../demo/`) and this production stack run **the same FastAPI application, unchanged**. DRISHTI reads its backends from environment variables at startup — `DATABASE_URL`, `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, and the graph/vector endpoints — so "going to production" means **pointing the same code at stronger infrastructure**, not rewriting it.

| Concern | Demo (free) | Production (this folder) |
|---|---|---|
| Relational + spatial DB | SQLite file | **PostgreSQL + PostGIS** |
| Graph / networks | NetworkX in‑process | **Neo4j** (+ Graph Data Science) |
| Semantic search / RAG | keyword + rapidfuzz | **Qdrant** vector store |
| Assistant | extractive, grounded (`none`) | **Claude** (`anthropic`) or **self‑hosted Llama** |
| Secrets | `.env` | **HSM / KMS** (keys never on disk) |
| Entry / TLS | single uvicorn process | **reverse proxy** (Caddy) with auto‑TLS |
| Hosting | Render free web service | **on‑prem / GovCloud**, autoscaled |

---

## Topology

```
                Internet / Gov network
                         │  443 (TLS)
                         ▼
                 ┌───────────────┐
                 │  Caddy proxy  │   automatic TLS, single public entrypoint
                 └───────┬───────┘
                         │  app:8000 (internal)
                         ▼
                 ┌───────────────┐
                 │   DRISHTI app │   the SAME demo code (FastAPI / uvicorn)
                 └──┬────────┬───┴───────┐
                    │        │           │
                    ▼        ▼           ▼
            Postgres+PostGIS  Neo4j     Qdrant
            crimes/persons/   networks  MO-linkage &
            vehicles, spatial communities  assistant RAG
```

See **`docker-compose.yml`** — every service is commented and wired with the variables from `.env.production.example`.

---

## Run it (reference deployment)

```bash
cd production
cp .env.production.example .env.production
#  ── edit secrets: Postgres password, LLM key, Neo4j password, DOMAIN ──
docker compose --env-file .env.production up -d
```

To load the bundled seed CSVs into Postgres on first boot (the seeder is DB‑agnostic — it reads `DATABASE_URL`):

```bash
docker compose --env-file .env.production run --rm app python scripts/seed_db.py
```

> This compose file is **illustrative and runnable‑in‑principle**: it stands up the real services and the real app image. A production rollout adds backups, secret injection from HSM/KMS, network policy, and observability — see below.

---

## How it reuses the demo code

- The `app` service builds from **`../demo`** using the **demo `Dockerfile`** — byte‑for‑byte the same application.
- The only difference is the **environment** the container receives:
  - `DATABASE_URL` → Postgres/PostGIS instead of SQLite.
  - `LLM_PROVIDER=anthropic` (+ key + model) instead of `none`.
  - Graph and vector endpoints (`NEO4J_URI`, `QDRANT_URL`) for the network/RAG paths.
- The same `scripts/seed_db.py` seeds Postgres because it builds its engine from `DATABASE_URL` — no code change.

There is **no production fork of the application**. That's the whole point: what you evaluate in the demo is what runs in production.

---

## Security & sovereignty posture

Aligned with the DRISHTI proposal for a state‑police deployment:

- **Sovereign hosting.** Runs **on‑prem or in GovCloud** inside the police network — citizen and case data never leave the jurisdiction. No third‑party SaaS dependency for the data plane.
- **Sovereign AI option.** The assistant can run a **self‑hosted Llama** on an on‑prem GPU (`LLM_PROVIDER` pointed at an internal gateway), so no prompt or record ever leaves the boundary. Claude is offered as a managed alternative where policy permits.
- **Secrets in hardware.** API keys, DB credentials and tokens are issued from an **HSM / KMS** and injected at runtime — never written to a `.env` on disk. The `.env.production.example` here is a documentation template only.
- **Grounded‑by‑construction AI.** The assistant answers **only** from retrieved records and **cites the FIRs** it used; it is instructed to **refuse** on empty context. Ingestion **reports missing fields, never fabricates** them. This discipline carries over unchanged from the demo.
- **Least exposure.** Only the reverse proxy binds public ports; Postgres, Neo4j and Qdrant are reachable solely on the internal Docker network. Add IP allow‑lists / mTLS at the proxy for the gov network.
- **Auditability & access control.** Production wires real citizen auth for MyShield (OTP / DigiLocker‑style), role‑based access for officers, and an audit trail of queries — the demo uses a placeholder token to stay frictionless.

---

## What now costs money

The demo is free; production has real, predictable costs:

| Item | Why it costs | Notes |
|---|---|---|
| **Managed / hosted PostgreSQL + PostGIS** | Replaces the free SQLite file | HA, backups, storage; cost scales with data volume |
| **Neo4j + Qdrant hosting** | Dedicated graph + vector services | Self‑hosted on the same nodes or managed |
| **LLM inference** | Claude API tokens, **or** an on‑prem **GPU** for self‑hosted Llama | GPU is a capital cost; Claude is per‑token |
| **Compute / hosting** | On‑prem servers or GovCloud instances (vs. a free Render dyno) | Autoscaling app + DB nodes |
| **HSM / KMS** | Hardware‑backed key custody | Required for sovereign secret handling |
| **Ops** | Backups, monitoring, TLS certs, on‑call | Standard for a production gov system |

Everything above is **infrastructure** spend. The DRISHTI application itself — the analytics, the grounded assistant, the ingestion honesty, the API contract — is identical to the free demo you can deploy today.
