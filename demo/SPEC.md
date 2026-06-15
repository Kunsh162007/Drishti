# DRISHTI Demo — Build Contract (single source of truth)

This file defines the **canonical data schema** and **API contract** that every part of the
demo must conform to. Backend, analytics, frontend, and data-generator are built against THIS.

## Tech (all free)
- Backend: **FastAPI** (Python), serves the API under `/api/*` and the static frontend at `/`.
- DB: **SQLite** by default (file committed with seed data), switchable to Postgres/PostGIS via `DATABASE_URL`.
- Analytics/ML: scikit-learn, h3, rapidfuzz, numpy, pandas (all free).
- Assistant: retrieval over the DB + **optional** LLM (`LLM_PROVIDER`); free/extractive when no key.
- Frontend: static HTML/CSS/JS using CDN libs — **MapLibre GL**, **deck.gl**, **sigma.js**, **Apache ECharts**. No build step.

## Environment variables (demo vs production switch)
| Var | Demo default | Production example |
|---|---|---|
| `DRISHTI_MODE` | `demo` | `production` |
| `DATABASE_URL` | `sqlite:///.../drishti_demo.db` | `postgresql://.../drishti` (PostGIS) |
| `LLM_PROVIDER` | `none` | `anthropic` / `groq` / `openai` |
| `LLM_API_KEY` | _(empty)_ | _(paid key)_ |
| `LLM_MODEL` | _(empty)_ | `claude-opus-4-8` / `llama-3.3-70b` |

## Canonical columns

### crimes
`fir_number` (str, unique) · `district` · `police_station` · `crime_type` · `crime_category`
· `severity` (1-5) · `latitude` (float) · `longitude` (float) · `h3_r7` · `h3_r8` · `h3_r9`
· `occurred_at` (ISO8601) · `reported_at` (ISO8601) · `hour` (0-23) · `day_of_week` (0=Mon)
· `modus_operandi` (text) · `description` (text) · `status` (Open/UnderInvestigation/ChargeSheeted/Closed)
· `victim_count` (int) · `accused_count` (int) · `property_value_inr` (float, nullable)
· `weapon_used` (str, nullable) · `source` (str)

### persons
`person_id` (str) · `fir_number` (FK) · `full_name` · `normalized_name` · `role` (Suspect/Accused/Victim/Witness/Complainant)
· `gender` · `age` (int, nullable) · `phone` (str, nullable) · `address` (nullable) · `district`
· `true_identity_id` (str — ground-truth identity for entity-resolution demo; NOT shown to users)

### vehicles
`vehicle_id` (str) · `fir_number` (FK) · `reg_number` · `vehicle_type` · `make_color` (nullable)

> Missing values must be stored as NULL / empty — **never** invented or defaulted. Ingestion reports missingness.

## API contract (all JSON; prefix `/api`)
- `GET  /health` → `{status, mode, db, records}`
- `GET  /meta` → `{districts[], crime_types[], categories[], date_range:{min,max}, totals:{crimes,persons,vehicles}}`
- `GET  /crimes` ?district&crime_type&category&date_from&date_to&q&limit&offset → `{total, items:[crime...]}`
- `GET  /stats` ?district&date_from&date_to → `{kpis:{...}, by_category:[{name,value}], by_district:[...], by_hour:[24], by_month:[...], by_status:[...]}`
- `GET  /hotspots` ?resolution(7-9)&crime_type&date_from&date_to → `{cells:[{h3, count, gi_score, significance, level('hot'|'cold'|'none'), lat, lng}]}`
- `GET  /emerging` ?resolution&period_days → `{cells:[{h3, lat, lng, category('new'|'intensifying'|'persistent'|'diminishing'|'sporadic'|'none'), recent, baseline, change_pct}]}`
- `GET  /timeseries` ?district&crime_type&interval(day|week|month) → `{points:[{period, count}]}`
- `GET  /anomalies` ?limit → `{items:[{fir_number, score, reasons[], crime...}]}`
- `GET  /risk` ?resolution → `{cells:[{h3, lat, lng, risk(0-1), drivers[]}]}`  (place-based, explainable)
- `GET  /network` ?fir&person&depth&limit → `{nodes:[{id,label,type('person'|'vehicle'|'crime'|'station'),meta}], edges:[{source,target,label}]}`
- `GET  /network/communities` → `{communities:[{id, members[], size, key_nodes[]}]}`
- `GET  /entity-resolution` ?threshold → `{pairs:[{a, b, score, evidence[], decision('auto'|'review'|'reject')}]}`
- `GET  /mo-linkage` ?fir&top_k → `{target:fir, matches:[{fir_number, similarity, shared_terms[], crime...}]}`
- `POST /assistant/chat` body `{message, session_id}` → `{answer, citations:[fir...], filter:{district?,crime_type?,date_from?,date_to?,hour_min?,hour_max?}, grounded:true, mode}`
- `POST /ingest` multipart file (csv/json/ndjson/geojson/xlsx) + optional `mapping` (JSON col map) → `{inserted, skipped, missing_report:{field:count}, errors[]}`
- `GET  /myshield` ?identifier(phone|reg_number|name)&token → `{matches:[own records], area_safety:{district, counts_by_type, nearest_hotspot}, disclaimer}`  (returns ONLY the requester's own records + de-identified area aggregates)

## Conventions
- Every crime dict returned includes all canonical columns.
- The assistant NEVER answers beyond retrieved records; it returns `citations` (FIR numbers) and a `filter` the map can apply.
- Analytics functions are **pure** (records in → results out); the backend does all DB I/O.
