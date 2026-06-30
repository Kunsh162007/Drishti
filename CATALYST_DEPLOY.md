# Deploying DRISHTI on Zoho Catalyst (AppSail)

> **Why this exists:** The KSP Datathon rules state — *"Deployment via Catalyst
> is mandatory for all submissions, without exception"* and *"using a third-party
> alternative when a Catalyst service is available may affect the validity of
> your submission."* Render is therefore a **development/reference** target only;
> the **graded deployment must run on Catalyst.** This guide migrates the working
> DRISHTI demo (FastAPI + bundled SQLite + static frontend) onto **Catalyst
> AppSail** with no code rewrite — only packaging and configuration.

---

## 1. DRISHTI → required Catalyst services

| DRISHTI capability | Required Catalyst service | Status in this guide |
|---|---|---|
| FastAPI backend (Docker) | **AppSail** (custom OCI runtime) | ✅ `catalyst/Dockerfile` + `app-config.json` |
| Static HTML/JS frontend | **Web Client Hosting / Slate** (or served by AppSail) | ✅ optional `client` block |
| Relational DB | **Data Store** | demo = bundled SQLite; prod = Data Store (env swap) |
| Assistant (LLM / RAG) | **QuickML** (LLM Serving, RAG) | prod env: `LLM_PROVIDER=quickml` |
| Tabular risk models | **Zia AutoML** | roadmap (place-based risk) |
| NLP on FIR text / OCR | **Zia Services** | roadmap (M-extended) |
| Officer login + RBAC | **Authentication** | prod tier |
| API routing / throttling | **API Gateway** in front of AppSail | prod tier |
| Scheduled bias audits | **Cron / Job Scheduling** | roadmap |
| Object/blob, report export | **Stratus** + **SmartBrowz** | roadmap |
| Custom domain + SSL | **Domain Mappings** | prod tier |
| CI/CD | **Pipelines** | optional |

The **critical, must-do** item for a valid submission is the first row:
**run the app on AppSail.** The rest map cleanly as you grow the platform.

---

## 2. Prerequisites

```bash
# Node 18+ then the Catalyst CLI
npm install -g zcatalyst-cli
catalyst --version

# Log in (opens browser)
catalyst login
```

Claim your hackathon credits first: <https://catalyst.zoho.com/promotions.html?cn=KSPH26>

---

## 3. One-time project init

From the repo root:

```bash
catalyst init
# - Select / create a project named "DRISHTI"
# - Choose the AppSail component when prompted
```

`catalyst init` writes the real project id into `catalyst.json`. The templates in
`catalyst/` show the intended shape — merge your generated values into them (or
point the generated config at `catalyst/Dockerfile` and `catalyst/app-config.json`).

---

## 4. Build & test the AppSail image locally

The AppSail image is built from the **repo root** (it needs `demo/`):

```bash
docker build -f catalyst/Dockerfile -t drishti-appsail .
docker run -p 9000:9000 -e X_ZOHO_CATALYST_LISTEN_PORT=9000 drishti-appsail
# open http://localhost:9000/            (frontend)
# open http://localhost:9000/api/health  (API)
```

AppSail injects the listen port via `X_ZOHO_CATALYST_LISTEN_PORT`; the container's
`CMD` already binds `0.0.0.0:$X_ZOHO_CATALYST_LISTEN_PORT`.

---

## 5. Deploy to AppSail

```bash
catalyst deploy
# or target just the app:
catalyst deploy --only appsail
```

After deploy, Catalyst prints the AppSail URL — that is the link to put on the
submission deck (replacing the Render URL). Set env vars in the Catalyst console
(**AppSail → drishti → Configuration → Environment Variables**) to match
`app-config.json`.

---

## 6. Demo vs Production (same codebase, config-only)

DRISHTI already reads everything from env vars (`demo/backend/config.py`), so the
demo→prod switch is configuration, not code:

| Env var | Demo (AppSail free) | Production (sovereign) |
|---|---|---|
| `DRISHTI_MODE` | `demo` | `production` |
| `DATABASE_URL` | *(unset → bundled SQLite)* | Catalyst **Data Store** / managed Postgres URL |
| `LLM_PROVIDER` | `none` (free, extractive) | `quickml` (Catalyst QuickML serving) |
| `LLM_MODEL` | — | QuickML model id |

> **Note on the demo DB:** AppSail container storage is ephemeral, so writes from
> the ingest endpoint do not persist across restarts in the demo tier — fine for a
> read-mostly demonstration. For persistence, point `DATABASE_URL` at **Catalyst
> Data Store** and load the schema with `demo/data/schema_ksp.sql` +
> `demo/scripts/build_ksp_schema.py` (the official KSP FIR schema).

---

## 7. Loading the official KSP schema into Catalyst Data Store (production)

The database is aligned to the official **Police FIR System** ER diagram
(`Police_FIR_ER_Diagram.pdf`). To stand it up on Data Store / Postgres:

```bash
# 1. create tables (translate SQLite affinity -> Postgres types per the comments in the DDL)
psql "$DATABASE_URL" -f demo/data/schema_ksp.sql

# 2. seed reference data + ETL from source records
python demo/scripts/build_ksp_schema.py "$DATABASE_URL"
```

See `demo/data/SCHEMA_MAPPING.md` for the full field-by-field crosswalk.

---

## 8. Checklist for a valid submission

- [ ] App deployed and reachable on **Catalyst AppSail** (not just Render).
- [ ] Submission deck links point at the **Catalyst AppSail URL**.
- [ ] Any capability with a matching Catalyst service uses that service
      (DB → Data Store, LLM → QuickML, auth → Authentication, …).
- [ ] Catalyst credits claimed via the KSPH26 promo link.
