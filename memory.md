# Project Memory — Personal Health Intelligence Agent

> **READ THIS FILE FIRST at the start of every work session, before touching anything.**
> It is the single source of truth for frozen decisions, schema, endpoints, the LangGraph
> graph, the work log, and the roadmap. Update the Work Log + Open Questions whenever state changes.

Capstone (B.E.) project. A **Health Intelligence Engine** that maintains a longitudinal
`PatientHealthState` — it *observes & explains* patient history. **It never diagnoses, predicts,
or prescribes.** All AI output is phrased as observations/patterns, never medical advice.

Design source of truth: `Docs/Project_Intro.md` + `Docs/WhatsApp Image ...jpeg` (architecture diagram).
Where the two conflict, the resolutions below win (see Architectural Decisions).

---

## 1. Tech Stack (FROZEN — do not change without logging a decision)

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| API framework | FastAPI + Uvicorn |
| Orchestration | LangGraph (sequential pipeline, deterministic) |
| Data validation | Pydantic v2 (PatientHealthState + sub-models) |
| Structured store | PostgreSQL |
| ORM / migrations | SQLAlchemy 2.x + Alembic |
| Vector store | ChromaDB |
| Embeddings | Chroma default local model `all-MiniLM-L6-v2` (sentence-transformers) — no API cost |
| LLM provider | **Anthropic Claude** (latest models) |
| — Reasoning/Narrative LLM | `claude-opus-4-8` (observations, health story) |
| — Intake parsing LLM | `claude-haiku-4-5-20251001` (cheap free-text → structured) |
| Auth | JWT (OAuth2 password flow), `passlib[bcrypt]` |
| PDF generation | ReportLab (deterministic template; doctor consultation summary) |
| Frontend | React + Vite + TypeScript |
| Charts | Recharts |
| Local infra | docker-compose (Postgres + Chroma) |
| Pkg mgmt (backend) | `uv` (or pip + venv) |

**Confirm Claude model IDs against the `claude-api` skill before writing any LLM call.**

---

## 2. Architecture Decisions (resolved ambiguities — chosen defaults)

These were genuinely open in the design doc; defaults chosen on 2026-06-29.

### D1 — Trend detection on numeric vitals: **Rolling-average delta**
Per vital sign (BP sys/dia, weight, HR, glucose, SpO₂):
```
recent_avg   = mean(last 3 readings)
baseline_avg = mean(prior 3 readings)
delta_pct    = (recent_avg - baseline_avg) / baseline_avg
trend = 'rising'  if delta_pct > +0.05
        'falling' if delta_pct < -0.05
        'stable'  otherwise
```
Persist `latest, recent_avg, baseline_avg, delta_pct, trend` in `vital_summary`.
Chosen over linear regression: no ML deps, trivially explainable in a viva. Thresholds (3-window,
±5%) live in config so they can be tuned per vital later.

### D2 — Memory Agent "tiered summaries + RAG": **Top-k semantic + bounded structured**
On each pipeline run the Memory Agent assembles ONE bounded context bundle:
- **Chroma:** `top_k = 5` semantically-similar past entries to the new input.
- **Postgres:** all Active Problems + latest Vital Summary (per vital) + Medication List
  + raw entries `WHERE date > now() - 6 months`.
Bundle is bounded (no full-history dump). `top_k` and the 6-month window live in config.
(Two-tier verbatim/summarized retrieval is a future upgrade — see Open Questions.)

### D3 — Postgres schema shape for flexible sections: **Hybrid (fixed columns + JSONB)**
Common, queryable fields are real typed columns (indexed); variable extras go in a JSONB
`attributes` column. Applies to `problems`, `vital_summary`, and similar "structured-ish"
tables. Avoids migrations for every new attribute while keeping core fields strongly typed.

### D4 — Diagram vs doc reconciliation, agent ↔ store write responsibilities: **Follow the diagram**
The diagram's data-flow labels are authoritative for who writes what:
- **Intake Agent** → *writes embeddings* to Chroma (embeds each new raw entry on ingest).
- **Memory Agent** → *reads/writes embeddings* (Chroma) + *writes JSON logs* to Postgres
  (persists an audit row: raw entry + the context bundle it assembled) + *returns records* to router.
  (Resolves the doc's "Memory is read-only" wording — Memory DOES write its JSON audit log.)
- **Reasoning Agent** → *writes alerts* + *reads logs* (Postgres only; no Chroma).
  "Alerts" = threshold-crossing flags → dedicated `alerts` table.
- **Response Agent** → *fetches from Postgres* (read-only render; no Chroma).
- **Doctor** → *fetch PDF* directly via FastAPI (dotted edge, bypasses dashboard).
- **Patient** → *enter symptoms* / *retrieve alert* via React Dashboard → FastAPI (REST).

### D5 — AI vs deterministic split (from doc §6, locked)
- **LLM:** Intake parsing, Reasoning observations, Response narrative/story. 
- **Deterministic Python:** all DB writes, trend math, problem-update rules, missing-info checks,
  output templating, PDF. Memory retrieval is embedding similarity (no generation).

---

## 3. PatientHealthState (Pydantic, in-memory shared state)

The LangGraph shared state object. Sections (from doc §4), each mirrors Postgres/Chroma:
`identity`, `medical_background`, `active_problems[]`, `resolved_problems[]`, `vital_summary{}`,
`symptom_clusters[]`, `trend_analysis[]`, `ai_observations[]`, `missing_information[]`,
`suggested_next_actions[]`. Plus pipeline-runtime fields: `new_entry` (from Intake),
`context_bundle` (from Memory), `output_type` (snapshot|story|pdf), `pending_question` (clarify branch).

---

## 4. Postgres Schema (tables)

Hybrid pattern (D3): typed columns + `attributes JSONB` where noted. All patient-owned tables carry
`patient_id` FK + `created_at`/`updated_at`.

| Table | Purpose / key columns |
|---|---|
| `users` | Auth (patients only — doctors have NO account; see `doctor_access`). `id, email, password_hash, role(patient), created_at` |
| `patients` | Identity/demographics. `id, user_id, name, age, sex, height, weight, blood_group, contact, attributes JSONB` |
| `medical_background` | Long-term context (rarely changes). `patient_id, conditions JSONB, allergies JSONB, family_history JSONB, surgical_history JSONB, lifestyle JSONB` |
| `medications` | Med list. `id, patient_id, name, dose, frequency, started_on, active(bool), attributes JSONB` |
| `entries` | Append-only raw intake audit (every symptom/vital/report/note as ingested). `id, patient_id, type, raw_text, structured JSONB, source, created_at` |
| `problems` | Active **and** resolved (status-discriminated). `id, patient_id, name, severity, frequency, trend, status(active/managed/resolved), first_seen, last_seen, resolved_at, attributes JSONB` |
| `vital_readings` | Raw numeric time series (feeds trend math). `id, patient_id, vital_type, value, unit, recorded_at, attributes JSONB` |
| `vital_summary` | Computed per-vital summary (D1). `id, patient_id, vital_type, latest, recent_avg, baseline_avg, delta_pct, trend, updated_at` |
| `symptom_clusters` | Co-occurring symptom groups. `id, patient_id, symptoms JSONB, occurrences, last_seen` |
| `observations` | AI free-text observations (non-diagnostic). `id, patient_id, text, evidence JSONB, created_at` |
| `alerts` | Reasoning "writes alerts" — threshold/flag events. `id, patient_id, kind, message, severity, vital_type, acknowledged(bool), created_at` |
| `missing_information` | Identified gaps. `id, patient_id, description, related_to, created_at, resolved(bool)` |
| `suggested_actions` | Informational cues. `id, patient_id, text, created_at, dismissed(bool)` |
| `reports` | Lab/report metadata (file on disk/object store; text embedded in Chroma). `id, patient_id, filename, path, report_type, summary, created_at` |
| `memory_log` | Memory Agent "writes JSON logs" — audit of each retrieval. `id, patient_id, entry_id, raw_entry JSONB, context_bundle JSONB, created_at` |
| `doctor_access` | Time-limited, patient-issued read tokens for doctors (no doctor login). `id, patient_id, token(unique), doctor_label(nullable), created_at, expires_at(default +7d), revoked(bool)` |

> `problems` covers both Active and Resolved Problems via `status` (doc's two sections = two
> logical views over one table). Resolved = `status='resolved'` + `resolved_at` set.

> **`entries` vs `memory_log` — NOT redundant, different concerns:**
> - **`entries`** = the permanent, append-only **source of truth** for what the patient submitted
>   and how the Intake Agent parsed it (`raw_text` + `structured` JSONB). One row per ingestion.
>   This is the canonical record; nothing else supersedes it.
> - **`memory_log`** = the Memory Agent's **retrieval audit** — what context it assembled *in
>   response to* an entry. `memory_log.raw_entry` is a **denormalized snapshot/reference** of the
>   triggering entry (copied for self-contained audit/debug), **not a second source of truth**;
>   the real value it adds is `context_bundle` (the top-k + bounded-structured pull). Joins back to
>   `entries` via `entry_id`. If `entries` and `memory_log.raw_entry` ever disagree, `entries` wins.

## 5. ChromaDB (vector store) — what lives here vs Postgres

**Chroma = semantic text only** (for similarity retrieval). Everything structured/numeric/audit = Postgres.

| Collection | Contents | Written by | Read by |
|---|---|---|---|
| `patient_entries` | Embedding of each raw entry text (symptom descriptions, notes). Metadata: `{patient_id, entry_id, type, date}` | Intake Agent | Memory Agent |
| `patient_reports` | Embedded report text chunks. Metadata: `{patient_id, report_id, report_type, date}` | Intake Agent (on report upload) | Memory Agent |

- **Postgres holds:** identity, demographics, medical background, medications, problems, vital readings + summaries, clusters, observations, alerts, missing info, suggested actions, report metadata, and all audit/JSON logs.
- **Chroma holds:** embeddings of free-text entries + report text, for top-k semantic recall only.

---

## 6. API Endpoints

Base prefix `/api`. Auth via JWT bearer. Ingestion endpoints (symptoms/vitals/reports) trigger the
LangGraph pipeline and return the resulting snapshot.

### Auth
- `POST /auth/register` — create user (patient/doctor)
- `POST /auth/login` — returns JWT
- `GET  /auth/me` — current user

### Patient profile / state
- `POST /patients` — create patient profile
- `GET  /patients/{id}` — profile
- `PUT  /patients/{id}` — update demographics
- `GET  /patients/{id}/state` — full PatientHealthState (assembled)
- `GET  /patients/{id}/background` — medical background
- `PUT  /patients/{id}/background` — update conditions/allergies/family/surgical/lifestyle

### Intake (pipeline-triggering + clarify branch)
- `POST /patients/{id}/intake` — submit free-text/structured input → runs pipeline → snapshot, OR returns a follow-up question (clarify branch)
- `POST /patients/{id}/intake/answer` — answer a pending follow-up; resumes pipeline

### Core CRUD (each create also feeds Intake/pipeline)
- `POST/GET/PUT/DELETE /patients/{id}/symptoms[/{sid}]`
- `POST/GET/PUT/DELETE /patients/{id}/vitals[/{vid}]` — vital readings (numeric)
- `POST/GET/DELETE     /patients/{id}/reports[/{rid}]` — upload + list lab reports (multipart)
- `POST/GET/PUT/DELETE /patients/{id}/medications[/{mid}]`
- `GET/PUT             /patients/{id}/history` — alias for medical background timeline

### Health state reads (Response Agent surface)
- `GET /patients/{id}/snapshot` — Health Snapshot (active problems, recent changes, observations, missing, next steps)
- `GET /patients/{id}/story` — Health Story narrative (LLM)
- `GET /patients/{id}/consultation/pdf` — Doctor Consultation Summary PDF (Doctor "fetch PDF")
- `GET /patients/{id}/problems?status=active|resolved` — problem list
- `GET /patients/{id}/vitals/summary` — computed vital summaries + trends
- `GET /patients/{id}/observations` — AI observations
- `GET /patients/{id}/alerts` — retrieve alerts (Patient "retrieve alert"); `POST .../alerts/{aid}/ack`

### Doctor access (token-based, no doctor account — OQ4)
Patient-authenticated (JWT) management:
- `POST   /patients/{id}/doctor-access` — generate a time-limited token (default 7d); returns shareable link/token + `doctor_label`
- `GET    /patients/{id}/doctor-access` — list issued tokens (active/expired/revoked)
- `DELETE /patients/{id}/doctor-access/{token_id}` — revoke a token

Doctor-facing, **gated by token only** (no JWT), **READ-ONLY**, scoped to Response Agent surfaces:
- `GET /shared/{token}/snapshot` — health snapshot
- `GET /shared/{token}/story` — health story
- `GET /shared/{token}/consultation/pdf` — doctor consultation PDF (the "fetch PDF" edge)

> Token endpoints expose ONLY snapshot/story/PDF. No CRUD, no raw entries, no writes, no other
> patient's data. Invalid/expired/revoked token → 403. This is the entire doctor surface.

### System
- `GET /health` — liveness

---

## 7. LangGraph Pipeline (nodes + edges)

Deterministic sequential pipeline (NOT an agent loop). Shared state = `PatientHealthState`.
Two explicit branch points only: intake-clarify (human-in-loop) and response output-type.

### Nodes
1. **`intake_node`** — LLM parse free-text → structured fact(s); normalize terms; split multi-symptom; detect missing critical fields. **Writes:** raw entry → `entries` (Postgres), embedding → `patient_entries`/`patient_reports` (Chroma). Sets `state.new_entry`.
2. **`clarify_node`** — (conditional) emits `pending_question`, interrupts to await user answer, then re-enters intake. Skipped if no critical field missing.
3. **`memory_node`** — assemble context bundle (D2): Chroma top-k=5 + bounded Postgres pull. **Writes:** `memory_log` JSON row (Postgres). Sets `state.context_bundle`; "returns records" to router.
4. **`reasoning_node`** — deterministic: update `problems` (increment freq / new / resolve), recompute `vital_summary` trend (D1 rolling-average), update `symptom_clusters`, check `missing_information`. LLM: generate `observations`. **Writes:** problems, vital_summary, clusters, observations, **alerts**, missing_information, suggested_actions (all Postgres). Updates full state.
5. **`response_node`** — (conditional on `state.output_type`) render snapshot | story (LLM) | pdf (ReportLab). **Reads:** Postgres only.

### Edges
```
START → intake_node
intake_node → clarify_node        [if critical field missing]
intake_node → memory_node         [else]
clarify_node → END                [interrupt; resumes at intake_node on answer]
memory_node → reasoning_node
reasoning_node → response_node
response_node → END
```

### LLM usage per node
- `intake_node`: Haiku (parse). `memory_node`: none (embeddings only).
- `reasoning_node`: Opus (observations only; trends/rules are pure Python).
- `response_node`: Opus/Sonnet for story + friendly snapshot; PDF is deterministic template.

---

## 8. Implementation Roadmap (by unit of work, not by session)

Ordered by dependency. A phase is "done" when it has a runnable/testable artifact.

### Phase 0 — Scaffolding & Tooling ✅ DONE (2026-06-29)
Backend venv/uv + deps; `.env` + Pydantic Settings; `docker-compose.yml` (Postgres + Chroma);
project layout (`backend/app/{api,models,schemas,db,vectorstore,core}`); ruff lint.

### Phase 1 — Backend Skeleton ✅ DONE (2026-06-29)
FastAPI app factory, settings, DB session (SQLAlchemy), Chroma client wrapper, `GET /api/health`
(real both-store readiness probe), Alembic wired to `Base.metadata`. App boots and connects to both
stores; verified end-to-end. *Depends: 0.*

### Phase 2 — Data Layer & Schema
All SQLAlchemy models (§4) + first Alembic migration; Pydantic `PatientHealthState` + sub-models (§3);
Chroma collections bootstrap (§5). *Depends: 1.*

### Phase 3 — Auth & Core CRUD
JWT auth (register/login/me, roles); patient profile + background; CRUD for symptoms, vitals, reports
(upload), medications, history — **persistence only, no pipeline yet**. *Depends: 2.*

### Phase 4 — LangGraph Pipeline + Memory
Wire the graph (§7) with `intake_node` (parse + Chroma write + entries write) and `memory_node`
(retrieval + `memory_log` write); clarify branch (interrupt/resume); state plumbing. Reasoning/Response
are pass-through stubs here. Ingestion endpoints now invoke the graph. *Depends: 3.*

### Phase 5 — Reasoning Engine
`reasoning_node`: rolling-average trend math (D1), problem update/resolve rules, symptom clustering,
missing-info checks, alerts on threshold crossings, LLM observations. Populates full state. *Depends: 4.*

### Phase 6 — Response + Outputs
`response_node` branch: snapshot endpoint, health story (LLM narrative), consultation PDF (ReportLab),
alerts retrieve/ack. Deterministic fallbacks for LLM failures. *Depends: 5.*

### Phase 7 — Frontend (React)
Vite+TS dashboard: auth, entry forms (symptoms/vitals/reports/meds), snapshot view, health story page,
vitals charts (Recharts), alerts panel, doctor PDF download. *Depends: 6 (API contracts stable).*

### Phase 8 — Integration, Hardening, Demo
Node-level error handling + LangGraph retries, seed/demo data, end-to-end test of full pipeline,
non-diagnostic-language audit, viva walkthrough script. *Depends: 7.*

> Phases 3 and the model work of 2 can overlap slightly; 7 can start against mocked API once 6's
> contracts are frozen. Otherwise treat as sequential.

---

## 9. Work Log (newest first)

- **2026-06-29** — **Backend Skeleton DONE** (roadmap Phase 0 + Phase 1). Built `backend/`:
  `pyproject.toml` (uv), `docker-compose.yml` (postgres:16 + chromadb/chroma), `.env(.example)`,
  Alembic wired to `Base.metadata`, FastAPI app (`app.main:app`) with `core/config.py`,
  `db/{base,session}.py`, `vectorstore/chroma.py`, `api/routes/health.py`. Verified end-to-end:
  `uv sync` ok, both containers healthy, `alembic upgrade head` clean (no tables yet by design),
  `GET /api/health` → 200 `{postgres:ok, chroma:ok}`; with Chroma stopped → 503 `{chroma:fail}`
  (readiness probe is real). Containers left running. **Env notes for next session:**
  (a) `uv` is installed at `~/Library/Python/3.12/bin/uv` (pip --user; not on default PATH — prepend it
  or use full path); (b) run the app on a port **other than 8000** (`uvicorn app.main:app --port 8001`)
  because Chroma's server owns localhost:8000; (c) start infra with `docker compose up -d` from `backend/`,
  needs Docker Desktop running (`open -a Docker`). Next: roadmap Phase 2 (Data Layer & Schema).
- **2026-06-29** — OQ4 (doctor authorization) RESOLVED: patient-issued time-limited read tokens
  (`doctor_access` table) → read-only `/shared/{token}/...` snapshot/story/PDF surface, no doctor login.
  Added table to §4 (now 16 tables), endpoints to §6. Schema/Chroma/endpoints/roadmap reviewed with
  user before Phase 2. OQ2/OQ3 intentionally left parked (Reasoning internals, not schema-shaping).
  Still no code.
- **2026-06-29** — Phase 1 (Planning) complete. Read `Project_Intro.md` + architecture diagram;
  cross-checked data-flow labels. Resolved 4 open ambiguities (D1–D4) with chosen defaults via
  AskUserQuestion. Created `backend/` + `frontend/` folders. Authored this `memory.md`
  (stack, decisions, schema, Chroma split, endpoints, LangGraph nodes/edges, roadmap).
  **No application code written.** Next: Phase 0 scaffolding.

---

## 10. Open Questions (unresolved — revisit before relevant phase)

- **OQ1 (pre Phase 4):** Two-tier retrieval (recent verbatim + pre-summarized older history) is a
  future upgrade over D2's bounded pull. Only build if context size becomes a real problem.
- **OQ2 (pre Phase 5):** Exact alert thresholds per vital (what BP/glucose/SpO₂ values flip an alert).
  Needs sane clinical-ish constants in config; not yet defined.
- **OQ3 (pre Phase 5):** "Resolved after X months quiescent" — set X (default proposal: 3 months
  no occurrence → auto-resolve). Confirm before coding the resolve rule.
- **OQ4 — RESOLVED 2026-06-29:** Doctor access = patient-issued, time-limited read tokens
  (`doctor_access` table, default 7-day expiry, revocable). Doctor visits `/shared/{token}/...`,
  gets READ-ONLY access to snapshot/story/PDF only — never CRUD/writes/raw data. No doctor login.
- **OQ5 (pre Phase 4):** Symptom-cluster definition — what time window counts as "co-occurring"
  (default proposal: symptoms logged within 48h grouped). Confirm.
- **OQ6 (pre Phase 1):** Confirm Claude model IDs + embedding model availability against `claude-api`
  skill before first LLM/embedding call.
