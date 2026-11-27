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
| LLM provider | **v2 (D15):** Claude via the owner's LiteLLM proxy — Haiku (`MODEL_FAST`) for routing/parsing, Sonnet (`MODEL_SMART`) for anything a person reads — with a Groq `llama-3.3-70b-versatile` fallback; one entry point `app/core/llm.py`. *(v1: Groq only, D7/D8.)* |
| Auth | JWT (OAuth2 password flow), `passlib[bcrypt]` |
| PDF generation | ReportLab (deterministic template; doctor consultation summary) |
| Frontend | React + Vite + TypeScript |
| UI components / styling | **shadcn/ui-style + Tailwind CSS** (SETTLED 2026-06-30; hand-written lean primitives in `src/components/ui.tsx`, not the CLI) |
| Charts | Recharts |
| Frontend data layer | **TanStack Query** (server state) + **axios** (`src/lib/api.ts`, JWT interceptor) + **react-router-dom** |
| Frontend E2E (dev) | **Playwright** (chromium) — used to verify each phase with screenshots |
| Local infra | Postgres 16 via docker-compose or a portable install (D26); Chroma embedded; `uv run python -m scripts.dev` |
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

### D6 — Primary keys: **integer `BigInteger` autoincrement** (SETTLED 2026-06-29)
All tables use integer surrogate PKs, not UUIDs. Not deployed publicly, so enumerable IDs are a
non-issue; doctors never see patient IDs (they use the random `doctor_access.token`). Closed — not an
open question.

### D7 — Intake LLM: **Groq (free tier)**, swapped from Claude Haiku (CHANGED 2026-06-30)
Intake parsing now uses **Groq** via its **OpenAI-compatible API** (`openai` client pointed at
`GROQ_BASE_URL=https://api.groq.com/openai/v1`), model `llama-3.3-70b-versatile` (config `INTAKE_MODEL`;
`llama-3.1-8b-instant` is the faster alt). Key env var: `GROQ_API_KEY`. **Reason:** free, very fast, and
good enough for structured free-text→JSON parsing. This is a deliberate change from the original
Claude-Haiku assumption in the frozen stack (superseded). **Scope:** Intake only — the Reasoning and
Response agents' LLM is NOT decided yet (see OQ7); do not assume Groq there.

### D8 — Reasoning + Response LLM: **Groq** (resolves OQ7, 2026-06-30)
Reasoning observations and Response narrative both use **Groq** `llama-3.3-70b-versatile`
(config `REASONING_MODEL`, `RESPONSE_MODEL`) — chosen for consistency with Intake (D7) and free tier;
quality adequate for non-diagnostic observations. **Caveat:** the Response health-story (Phase 6) is the
most quality-sensitive output; re-evaluate narrative quality there and swap provider only if it disappoints.
No Anthropic calls anywhere yet.

### Reasoning constants (resolved parked OQs, 2026-06-30; all config-driven, tunable)
- **OQ2 → alert thresholds** (`ALERT_THRESHOLDS`): bp ≥140/≥90 → `high_bp` (≥180/≥120 → `critical_bp`);
  glucose ≥200 → `high_glucose`, ≤70 → `low_glucose`; spo2 <92 → `low_spo2`; hr >100 → `tachycardia`,
  <50 → `bradycardia`. Phrased as flags, never diagnoses.
- **OQ3 → auto-resolve:** active problem `last_seen` older than **90 days** → `resolved` (`RESOLVE_AFTER_DAYS=90`).
- **OQ5 → symptom clusters:** symptoms within **48h**, min 2 distinct → cluster (`CLUSTER_WINDOW_HOURS=48`).

### D9 — `GET /patients/me` for patient-id resolution (SETTLED 2026-06-30, Phase 7)
`/auth/me` returns the user, but every `/patients/{id}/*` route needs the **patient id**. `GET /patients/me`
returns the current user's `Patient` (**404** if none → frontend routes to onboarding). Declared before
`/{patient_id}` so the literal "me" wins. Chosen over embedding patient in `/auth/me` (cleaner REST, keeps
user/patient concerns separate).

### D10 — CORS via FastAPI `CORSMiddleware` (SETTLED 2026-06-30, Phase 7)
Backend enables `CORSMiddleware` with origins from `CORS_ORIGINS` (default `http://localhost:5173,5174`).
Dev primarily uses the **Vite proxy** (`/api`→:8001, same-origin, no CORS needed), but CORS is on as
belt-and-suspenders so the API also works cross-origin / unproxied. `allow_credentials=True`, all methods/headers.

### D11 — Test isolation: **separate `phia_test` DB** (SETTLED 2026-06-30, Phase 8)
`backend/tests/conftest.py` creates/drops a dedicated `phia_test` database per session, points the app engine
at it (env override + settings cache clear before app import), stubs the vectorstore + Groq (offline/deterministic).
The demo DB (carol/Dana) is never touched. Run: `uv run pytest`.

### D12 — Non-diagnostic enforcement: **prompts + runtime filter + audit** (SETTLED 2026-06-30, Phase 8)
Defense in depth: tightened intake/reasoning/story prompts; `app/services/language_guard.py` denylist;
`observations.generate_observations` **drops** any candidate flagged as diagnostic before insert (logged);
`scripts/audit_language.py <pid>` scans stored obs + generated story, exits nonzero on any violation.

### D14 — Medication intelligence data sources (SETTLED 2026-06-30, user-confirmed)
Safety-sensitive feature; sources researched and confirmed before building.
- **Drug-drug interactions: DDInter 2.0** (`https://ddinter2.scbdd.com/`, SCBDD). Local table imported from the
  official ATC CSVs (schema `DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level`; Level∈Major/Moderate/Minor/Unknown).
  **License: CC BY-NC-SA 4.0** — fine for this **non-commercial academic capstone**, but caveats: must
  **attribute/cite** DDInter 2.0 (NAR 2025, PMC11701621); **ShareAlike** (any redistributed derivative must carry
  the same license — so the CSVs are **gitignored, not vendored** in-repo, re-downloaded by the import script);
  **no commercialization** without permission. Rejected: RxNav DDI API (dead since Jan 2024); DrugBank academic
  (CC BY-NC but gated behind slow human approval); third-party GitHub mirrors (no clean provenance).
- **Name normalization: RxNorm/RxNav** (`https://rxnav.nlm.nih.gov/REST/`, free, no key, live) — name→ingredient.
- **Per-drug reference (#1): curated, MedlinePlus-cited static table** (no LLM pharmacology).
- **HARD RULE (enforced + tested):** interactions surfaced ONLY from the DDInter table; no LLM in the path; a
  missing pair is "No known interaction found in DDInter 2.0" — **never "safe"**; everything framed "discuss with
  your doctor or pharmacist" + visible disclaimer.

### D13 — LLM resilience: **client timeout/retries + node fallbacks** (no LangGraph RetryPolicy) (Phase 8)
`groq_client` uses `LLM_TIMEOUT=30` + `LLM_MAX_RETRIES=2`. `intake.parse_entry` degrades to the deterministic
fallback on Groq failure (never 500s); `/intake` route wraps the graph in try/except → clean **502** on
unexpected failure. Observations + story already had fallbacks. Verified by fault injection.

### v2 decisions (2026-11-27, Phase 0–1; the v2 task list is ROADMAP.md)

### D15 — LLM routing: **LiteLLM first, Groq fallback, one entry point** (supersedes D7/D8)
Every LLM call goes through `app/core/llm.py::llm_json(task, system, user)`. The task picks a tier from
`LLM_TASK_TIERS` (config; a partial `.env` override keeps the defaults) and the tier picks the model:
`MODEL_FAST` (Haiku: router, intake, report_extract), `MODEL_SMART` (Sonnet: story, observations,
report_summary, drug_reference), `MODEL_VISION` (Phase 4). Calls go to the LiteLLM proxy (`LLM_BASE_URL`,
`LLM_API_KEY`; 5 s connect timeout, 1 retry, so failover is quick), and on ANY error, including an unparseable
reply, to Groq `FALLBACK_MODEL` (`llama-3.3-70b-versatile`; key `FALLBACK_API_KEY`, the v1 name `GROQ_API_KEY`
still works). Replies are parsed leniently (code fences / stray prose). Every call logs task, provider, model,
tokens, cost (LiteLLM's `x-litellm-response-cost` header, else the `LLM_PRICES` table) and latency to the log and
`backend/llm_usage.jsonl` (gitignored; never prompt text). Callers check `is_available()` and keep their own
deterministic fallback. Tests make constructing a real client raise. Model names default to
`claude-haiku-5-5` / `claude-sonnet-5-5` and must be checked against the proxy (`scripts.llm_smoke_test --list-models`).

### D16 — App clock + IST calendar days
`app/core/clock.py`: `now()` (aware UTC), `frozen_at(dt)` (process-wide, for the Phase 7 replay), `today()` /
`to_local()` in `APP_TIMEZONE` (Asia/Kolkata). Store UTC, use IST for calendar days (med schedule, onset words,
seed). Model `created_at`/`updated_at`/`taken_at` get a Python default `clock.now` (Postgres `now()` stays as the
server default, so no migration) so a frozen replay writes past timestamps. Auth stays on real time on purpose
(`core/security.py`, `api/deps.py`, doctor-access expiry), as does the LLM usage log.

### D17 — Backdating: **`entries.occurred_at`; the LLM quotes, code resolves**
`occurred_at` = when it happened; `created_at` = when it was logged (backfilled = created_at). Intake asks the
LLM only to quote the onset words (`attributes.onset`); `services/onset.py` resolves them deterministically:
yesterday (midday), last night (22:00), this morning (08:00), since Monday, N days/hours/weeks ago, "for/since N
days" (Indian English), 12 March / March 12. Read in IST, stored UTC, never in the future, ignored if > 1 year
(history, not an episode). Timeline, problems, clusters, memory, PDF and the Chroma `date` metadata all use it.

### D18 — Problems: **canonical names + frequency trend**
`app/data/symptom_synonyms.py` maps only true equivalents (headaches / head pain → headache; migraine stays
separate). Intake stores the canonical name (+ `reported_name`); problems match on canonical name or alias and
remember new variants as aliases; `problems.entries_for_problem` is the one episode lookup. Trend = episodes in
the last 30 days vs the per-30-day rate in the 30–90 days before; moves only on a difference of ≥ 1 episode a
month; `None` until 2 episodes. Recomputed for every active problem each pipeline run, so it also comes down;
problems without symptom episodes (vitals-based, managed) keep their trend.

### D19 — Clusters are **symptom pairs**, counted once per episode
For each pair of different (canonical) symptoms: the number of separate episodes in which both were logged within
`CLUSTER_WINDOW_HOURS` (48 h) of each other by `occurred_at`; repeats inside one window count once. Recomputed
from entries on each symptom log (handles backdating); old multi-symptom rows are replaced.

### D20 — Medication history + prescriber
`medication_events` (start / stop / dose_change, `event_date` IST day, old → new dose, prescriber, source
manual | visit_note, note). Create records a start; update records dose change / stop / restart, dated by an
optional `changed_on`. Deleting a medicine = removing a mistaken entry (cascades its events); stopping is the
"it ended" path and is recorded. `medications.prescriber` + `prescriber_specialty` for cross-doctor checks (Phase 5).

### D21 — Router before intake: **log / question / both**
Fast tier when available, else a deterministic heuristic (question marks; wh-words only in question form;
auxiliaries only before a subject, so "Have been dizzy…" stays a log). Questions are not saved; until the
Phase 2 assistant they get a fixed holding reply (status `question`). "both" is logged and the asked part returned
as `user_question`. `/intake/answer` skips the router (clarification answers are always logs).

### D22 — Context tags at intake (fixed vocabulary)
`skipped_meal, delayed_meal, poor_sleep, stress, missed_dose, alcohol, exercise, travel` (`delayed_meal` added
for Harsh's "skipping or delaying lunch"). LLM-picked tags are vocabulary-checked and unioned with keyword rules
(`services/context_tags.py`, tested against false positives such as "running nose" or "blood pressure").
Stored in `entries.structured.context_tags` (JSONB, no migration) for the Phase 2 recurrence detector.

### D23 — Language guard: narrower "you have" + opt-in doctor attribution
"you have …" only trips when a condition word follows, never on "you have logged/had/recorded…".
`is_diagnostic(text, allow_attributed=True)` skips sentences that clearly relay a doctor ("Dr. Rao
diagnosed…", "According to your doctor…"). Opt-in only, for confirmed visit-note text (Phase 3), never for AI
text, so a diagnosis can't be laundered through a doctor's name.

### D24 — Missing info resolves; suggestions are dismissable (14-day cooldown, user-decided)
A BP gap closes once a reading exists (intake or the vitals form) and its "Log today's blood pressure"
suggestion is auto-dismissed. `POST …/suggested-actions/{id}/dismiss`; a dismissed suggestion is not re-added for
14 days (`suggested_actions.dismissed_at`).

### D25 — One BP alert per reading
Both halves of one reading → one alert ("BP 147/92 is above the alert threshold", the worse half sets the level,
`vital_type = blood_pressure`); its context lists whole readings. A lone half from the vitals form still alerts
on its own until Phase 6 makes BP one field.

### D26 — Local environment (owner's Windows machine)
No Docker and no admin rights: Postgres 16 runs from EDB's portable zip at `%LOCALAPPDATA%\phia-postgres`
(`LOCAL_PG_HOME`); Docker users keep `docker compose up -d`. Chroma runs embedded (`CHROMA_MODE=embedded`,
compose = Postgres only); stop the API before seeding (single writer). One command: `uv run python -m
scripts.dev` (Postgres → create DB → migrate → seed if missing → API :8001 + web :5173). Python pinned to 3.11.
Git is local only and never pushed (the machine's GitHub is a company account); commits use a placeholder author.

### D27 — Choices for things the roadmap didn't cover (user-confirmed 2026-11-27)
The three existing LLM calls missing from the model plan (observations, report summary, AI drug-reference
fallback) use the smart tier. `MED_AI_FLAGS_ENABLED` defaults to false until Phase 5. Questions get a holding
reply until Phase 2 (D21). Dismissed suggestions stay away 14 days (D24).

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

**v2 additions (Phase 1):** `entries.occurred_at` (when it happened; D17) ·
`suggested_actions.dismissed_at` (D24) · `medications.prescriber`, `prescriber_specialty` (D20) ·
`medication_events` (`id, patient_id, medication_id, medication_name, event_type start|stop|dose_change,
event_date, old_dose, new_dose, prescriber, source manual|visit_note, note, created_at`; D20). Also in the
schema since v1 but not listed above: `dose_logs` (adherence) and `drug_interactions` (DDInter reference).
`entries.structured` now also carries `context_tags` (D22) and `reported_name` (D18).

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
- `POST /patients/{id}/intake` — submit free-text/structured input → runs pipeline → snapshot, OR returns a follow-up question (clarify branch). **Response (`IntakeOut`) surfaces** `new_entry` (extracted), `context_bundle.semantic_matches` (Memory RAG hits), **and `reasoning_summary`** (newly-created observations/alerts) — the Log thread renders these inline.
- `POST /patients/{id}/intake/answer` — answer a pending follow-up; resumes pipeline (stateless re-invoke on the accumulated transcript; frontend caps at 3 follow-ups)
- `GET  /patients/{id}/entries?limit&offset` — full append-only entry history (all types, newest-first); read-only projection for the Log thread

### Core CRUD (each create also feeds Intake/pipeline)
- `POST/GET/PUT/DELETE /patients/{id}/symptoms[/{sid}]`
- `POST/GET/PUT/DELETE /patients/{id}/vitals[/{vid}]` — vital readings (numeric)
- `POST/GET/DELETE     /patients/{id}/reports[/{rid}]` — upload + list lab reports (multipart)
- `POST/GET/PUT/DELETE /patients/{id}/medications[/{mid}]`
- `GET /patients/{id}/medications/intelligence` — per-drug reference (curated, MedlinePlus-cited) + **sourced** drug-drug interaction flags from the local DDInter 2.0 table (no LLM; missing pair → "no known interaction found", never "safe"). Declared before `/{mid}`. (D14)
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

### v2 additions (Phase 1)
- `POST /patients/{id}/intake` — may now return `status: "question"` (not saved; `reply` is a holding message
  until Phase 2) or `user_question` alongside a processed log (router, D21).
- `GET /patients/{id}/suggested-actions` · `POST /patients/{id}/suggested-actions/{aid}/dismiss` (D24)
- `GET /patients/{id}/medications/events?days&medication_id` — start/stop/dose-change history (D20)
- Entry outputs (`/entries`, `/symptoms`, timeline detail) include `occurred_at` (D17).

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
START → router_node               (v2, D21: log | question | both)
router_node → question_node       [question: not saved; holding reply until Phase 2]
router_node → intake_node         [log / both]
question_node → END
intake_node → clarify_node        [if critical field missing]
intake_node → memory_node         [else]
clarify_node → END                [interrupt; resumes at intake_node on answer, router skipped]
memory_node → reasoning_node
reasoning_node → response_node
response_node → END
```

### LLM usage per node (v1 notes below; in v2 every call goes through `llm_json(task)`, D15)
- `intake_node`: **Groq** `INTAKE_MODEL` (parse). `memory_node`: none (embeddings only).
- `reasoning_node`: **Groq** `REASONING_MODEL` (observations only; trends/rules are pure Python).
- `response_node`: **Groq** `RESPONSE_MODEL` for the **health story** only. **Snapshot is a deterministic
  template** (no LLM); **PDF is a deterministic ReportLab template** (no LLM). Story has a deterministic
  fallback when Groq fails/no key.

---

## 8. Implementation Roadmap (by unit of work, not by session)

> v1 build phases (all done). The **v2** task list lives in `ROADMAP.md`; v2 decisions are D15 onward.

Ordered by dependency. A phase is "done" when it has a runnable/testable artifact.

### Phase 0 — Scaffolding & Tooling ✅ DONE (2026-06-29)
Backend venv/uv + deps; `.env` + Pydantic Settings; `docker-compose.yml` (Postgres + Chroma);
project layout (`backend/app/{api,models,schemas,db,vectorstore,core}`); ruff lint.

### Phase 1 — Backend Skeleton ✅ DONE (2026-06-29)
FastAPI app factory, settings, DB session (SQLAlchemy), Chroma client wrapper, `GET /api/health`
(real both-store readiness probe), Alembic wired to `Base.metadata`. App boots and connects to both
stores; verified end-to-end. *Depends: 0.*

### Phase 2 — Data Layer & Schema ✅ DONE (2026-06-29)
All 16 SQLAlchemy models (§4) + first Alembic migration `b7b529cb8dea` (applied, verified, no drift);
Pydantic `PatientHealthState` + sub-models (§3). *Depends: 1.*
**Note:** Chroma collections (§5) bootstrap deferred to the unit that first writes embeddings (Phase 4),
not done here — Phase 2 was Postgres-side only.

### Phase 3 — Auth & Core CRUD ✅ DONE (2026-06-29)
JWT auth (register/login/me); patient profile + background/history; CRUD for medications, vitals,
symptoms (→entries), reports (multipart upload). Persistence only, no pipeline. Ownership-guarded,
verified group-by-group against live DB. *Depends: 2.*

### Phase 4 — LangGraph Pipeline + Memory ✅ DONE (2026-06-30)
Graph wired (§7) with `intake_node` (Groq parse + entries write + Chroma embed) and `memory_node`
(top-k retrieval + bounded Postgres + `memory_log` write); clarify branch via stateless re-invoke;
reasoning/response stubbed. `/intake` + `/intake/answer` live. Chroma collections (§5) bootstrapped here.
Verified with offline fallback parser; real Groq path pending user's `GROQ_API_KEY`. *Depends: 3.*

### Phase 5 — Reasoning Engine ✅ DONE (2026-06-30)
`reasoning_node` + `app/services/*`: rolling-average trend math (D1), problem update/auto-resolve (OQ3),
symptom clustering (OQ5), missing-info + suggested actions, threshold alerts (OQ2), Groq observations (D8).
Verified end-to-end via `/intake`; BP parsing hardened (prompt + regex recovery). *Depends: 4.*

### Phase 6 — Response + Outputs ✅ DONE (2026-06-30)
Shared `assemble_state` backbone → snapshot (deterministic), health story (Groq + fallback), consultation
PDF (ReportLab), alerts retrieve/ack, doctor token `/shared/*`, §6 state reads. Observations deduped.
All outputs consistent (one assembler). Verified end-to-end. Outputs are on-demand REST; `response_node`
stays a stub. *Depends: 5.*

### Phase 7 — Frontend (React) ✅ DONE (2026-06-30)
Vite+TS+Tailwind SPA: auth+onboarding, intake+forms, dashboard snapshot+alerts, vitals charts (Recharts),
story (+fallback badge), doctor sharing (token + DoctorView + PDF). Real backend (Vite proxy), no mocks.
Added backend `GET /patients/me` + CORS. Verified per-group via Playwright screenshots. *Depends: 6.*

### Phase 8 — Integration, Hardening, Demo ✅ DONE (2026-06-30)
Pipeline error handling/degradation (D13), idempotent seed (`scripts/seed_demo.py` → demo@phia.health),
pytest suite vs `phia_test` (D11), non-diagnostic guard + audit (D12), loose-ends fixed. *Depends: 7.*
**Viva/teaching docs intentionally deferred** — a separate doc pass on explicit request, NOT part of Phase 8.

> **Demo login:** patient `demo@phia.health` / `demo-pass-123` (re-run `uv run python -m scripts.seed_demo`
> to (re)populate). Backend `:8001`, frontend `:5173` (`npm run dev`), containers via `docker compose up -d`.

> Phases 3 and the model work of 2 can overlap slightly; 7 can start against mocked API once 6's
> contracts are frozen. Otherwise treat as sequential.

---

## 9. Work Log (newest first)

- **2026-11-27** — **v2 Phase 0 + Phase 1 (Claude Code session).** 30 commits on `v2` (one per task);
  `main` = untouched v1. Decisions D15–D27 above.
  **Setup:** local git only (never pushed; placeholder author until the owner re-authors); ROADMAP.md moved into
  the repo; CLAUDE.md holds the standing rules. This Windows machine has no Docker and no admin rights, so:
  uv via winget, Python pinned to 3.11, Postgres 16.16 from EDB's portable zip at `%LOCALAPPDATA%\phia-postgres`
  (`LOCAL_PG_HOME`), Chroma embedded. One command: `uv run python -m scripts.dev`.
  **Baseline:** migrations clean, `alembic check` no drift, app healthy on :8001/:5173. Found and fixed, before
  feature work: (1) the test suite made live calls (DDInter download thread at every TestClient startup, RxNav in
  a med test); now stubbed and a real LLM client can't be built in tests; (2) consultation PDF 500'd on Windows
  (`strftime("%-d")`); (3) the DDInter import crashed on Windows consoles (cp1252 vs a Unicode arrow), so first
  boot silently fell back to the 13 critical pairs forever; the full import now loads 152,843 pairs (25,792 Major).
  **Phase 1 done:** embedded Chroma; README + one-command runner; v2 LLM settings + `llm.py` rewrite (all 6 call
  sites, smoke-test script, usage log); app clock; IST calendar days; backdating (`occurred_at` + onset parser);
  context tags; canonical symptom names + aliases; frequency-based problem trend; pair clustering; missing-info
  auto-resolve + suggestion dismiss (14-day cooldown); narrower language guard + opt-in doctor attribution; one BP
  alert per reading; prescriber per medicine; `medication_events` history; router (log/question/both, holding
  reply for questions); observations see dated past entries; story fallback `None` fix; vitals labels + padded
  y-axis; timeline opens at newest; seed times of day. Migrations: `f3501e2ab2f5` (occurred_at), `4c29f0f2bfd0`
  (dismissed_at), `3e19f634c1f5` (prescriber), `9051870398ab` (medication_events).
  **Verified:** ruff clean; **177 tests pass** (was 34), all offline; `alembic check` no drift; migration
  round-trip down/up OK; `npm run build` clean. In the browser (offline, no keys): one "BP 147/92" alert, dismiss
  button, timeline scrolled to newest, labelled charts with padded axes, a log of "…yesterday…" shows "happened
  <yesterday>", a question gets the holding reply and is not saved.
  **Pending keys (`backend/.env`: LLM_BASE_URL, LLM_API_KEY, FALLBACK_API_KEY):** `scripts.llm_smoke_test
  --list-models --fallback` to confirm model names + JSON mode through the proxy; one real LLM story; a real
  router/intake check with Haiku.
  **Known issues for later:** `rxnorm.normalize_ingredient` caches a network-failure fallback as if it were the
  answer (3 names hit during this import; fix with Phase 5's RxNorm work); the PDF's vital-trends table still
  prints raw keys (Phase 6 "no raw keys"); the offline intake parser files everything as a `note`; the Response
  agent is still a pass-through (Phase 2) and the seed's observations are canned (Phase 7 replay).
- **2026-07-01** — **Part 3: expose report intelligence through the API (for Part-4 frontend).** Committed.
  Reshaped the patient-scoped report endpoints (paths stay `/patients/{id}/reports*` — the whole app is
  ownership-guarded via `OwnedPatient`; the requirement's bare `/reports` was shorthand). **(1) List**
  `GET /patients/{id}/reports` now returns a **trimmed `ReportListItem`** (was full `ReportOut`): id,
  patient_id, filename, status, report_type, test_date, ai_summary, `flagged_values` (only `flag != "normal"`,
  **capped at 3**, high/low ranked above unknown), `flagged_count` (total, may exceed 3), parse_error,
  created_at (upload date). Now ordered **newest-first** (`id desc`). **(2) Detail** `GET /.../reports/{id}`
  returns new **`ReportDetail`**: ALL `extracted_values`, status, ai_summary, parse_error, + a **`download_url`**
  (`/api/patients/{id}/reports/{id}/file`, the existing FileResponse route) instead of leaking the raw disk
  `path`. **(3) Upload** `POST /.../reports` unchanged from the user's POV (still 201 immediately with full
  `ReportOut`, status `uploaded`) — already kicked off the Part-1 `parse_report` BackgroundTask. **(4) Stuck-parse
  guard:** `parse_report` already sets `status=failed`+`parse_error` on any exception (never stuck), BUT a
  process crash/restart mid-parse would orphan a row in `parsing` forever (BackgroundTasks don't survive a
  restart). Added `reconcile_orphaned_parses()` (report_extraction.py), called from the **lifespan startup**
  (best-effort) → flips any leftover `parsing` → `failed` with a clear "interrupted, please re-upload" message.
  Schemas in `schemas/report.py` (`ReportListItem`, `ReportDetail`, `FlaggedValue`; `ReportOut` kept for upload).
  No DB/migration change. Frontend `Report` type + ReportsPage only read id/filename/report_type/created_at, so
  the richer list shape is a backward-compatible superset (Part 4 will render status/ai_summary/flagged).
  **Live manual test (demo@phia.health, pid 15, real Groq):** uploaded a lipid panel → 201 `uploaded` instantly
  → background-parsed to `parsed` (report_type "Lipid Panel", test_date 2026-06-20, 4 values, ai_summary
  non-diagnostic, 3 flagged high shown/3 total); detail returned all 4 values + working `download_url` (HTTP 200);
  a binary `.dat` upload → `failed` + `parse_error`, never stuck; forced a row to `parsing` + restarted server →
  reconciliation logged "marked 1 stuck report(s) as failed" and flipped it. Deleted the junk report; **kept the
  parsed lipid panel (id 16) as real Part-4 demo content.** ruff clean; **34 pytest pass**; alembic no drift.
- **2026-07-01** — **Report intelligence pipeline (Parts 1 + 2). Committed.** Turns uploaded reports from a
  dumb file store into a real pipeline ingestion point. **Part 1 (extraction):** `services/report_extraction.py`
  — `pypdf` text extraction (scanned/image PDFs raise `OcrRequiredError`, a flagged **TODO**, never a silent
  empty parse); Groq structured-extraction (`report_type`/`test_date`/`values[]` of
  `{test_name,value,unit,reference_range,flag∈normal|high|low|unknown}`; non-lab docs → `values:[]`). Extended
  `reports` table (migration `c3e4f5a6b7d8`): `status(uploaded→parsing→parsed|failed)`, `test_date`,
  `extracted_text`, `extracted_values` JSONB, `parse_error`. Parsing runs as a **FastAPI BackgroundTask** after
  upload responds (never blocks on Groq). **Part 2 (make findings visible to the agents):**
  (1) **Chroma indexing** — `services/report_indexing.py` chunks each parsed report into one summary chunk +
  one per lab value, upserts into the **`patient_reports`** collection (memory.md §5) tagged
  `patient_id/report_id/date/report_type/test_name/flag` (idempotent: deletes prior chunks by `report_id` first).
  (2) **Memory retrieval GAP FOUND & FIXED** — `memory_node` only queried `patient_entries`, so report chunks
  in `patient_reports` were invisible; added `_report_matches()` (top-k over `patient_reports`) →
  `context_bundle.report_matches` + `context_bundle.lab_trends`. This realizes §5's "patient_reports read by
  Memory Agent", which was never actually wired. (3) **Lab trends REUSE the vitals module** — new
  `record_lab_readings_and_recompute()` in `services/vitals_trend.py` writes each numeric lab result as a
  `VitalReading` with `vital_type="lab_<slug>"` (dated at `test_date`) and calls the SAME `recompute_summary`
  (D1 rolling-average) — recurring tests (e.g. LDL across panels) trend exactly like a vital. **Note:** D1 needs
  ≥4 readings for a non-stable trend (recent-3 vs prior window); exactly 3 → "stable" (no baseline window).
  (4) **`ai_summary`** (migration `d4f5a6b7c8e9`) — one extra Groq call at parse time → 1-2 sentence
  plain-language, **non-diagnostic** takeaway (language-guarded; deterministic fallback when Groq off/flagged),
  fed the cross-report trend so it says "trending up since <first panel date>". `observations.py` now consumes
  `context_bundle.report_matches` + splits real vitals from `lab_*` series so Reasoning can **cite reports**.
  **Sanity check (`scripts/sanity_report_intelligence.py`, live Postgres+Chroma+Groq):** 4 lipid panels
  (LDL 128→176) → LDL trend `rising` (+26.6%) via the vitals module; `ai_summary` "trending up since
  February 10, 2026"; Memory retrieval returns 5 report chunks incl. all LDL values; full-graph run on a
  complete symptom entry → observation **"LDL Cholesterol was 176 mg/dL on the latest lipid panel and has
  trended upward across reports"** (cites the report, not vitals). **Gotcha:** the pipeline is ingestion-driven
  — a bare *question* ("what's my cholesterol trend") hits the intake-parse gate → clarify branch, never reaching
  Memory/Reasoning; the honest check logs a complete entry (and calls `memory_node` directly to isolate
  retrieval). ruff clean; **34 pytest pass** (+8 new offline tests in `test_report_intelligence.py`); alembic no
  drift; reports collection stubbed in conftest. **Deferred to later parts:** frontend surfacing of
  status/ai_summary/values; OCR fallback.
- **2026-06-30** — **Medication intelligence (safety-sensitive; reference info + sourced DDI flags).** Not
  committed. **Verified live (Playwright, 0 console errors); 14 pytest pass (incl. 2 new safety-boundary tests).**
  **Source research → user-confirmed (see D14).** **Backend (NO LLM anywhere in this feature):**
  new `drug_interactions` reference table (`models/reference.py`, migration `977d1af8bd80`) holding the local
  **DDInter 2.0** dataset — **160,235** deduped pairs (Major/Moderate/Minor/Unknown), imported by
  `scripts/import_ddinter.py` (downloads the 8 official ATC CSVs to a **gitignored** `data/ddinter/`, parses
  with csv module, keeps most-severe per pair). `services/rxnorm.py` = RxNav name→ingredient normalization
  (live, cached, **degrades to lowercased raw name** on any network failure — never blocks/500s).
  `data/drug_reference.py` = **16 curated, MedlinePlus-cited** per-drug entries (used_for/timing/considerations),
  all pass the language guard. `services/med_intel.py` orchestrates: per-drug reference + pairwise lookup;
  **known pair → level + "discuss with your doctor or pharmacist"; missing pair → "No known interaction found
  in DDInter 2.0" (NEVER "safe")**. Route `GET /patients/{id}/medications/intelligence` (declared BEFORE
  `/{med_id}` so the literal segment wins). **Frontend:** `MedicationIntelligence.tsx` on MedicationsPage —
  prominent amber disclaimer, interaction list (severity-colored badges; Unknown→"severity not classified"),
  explicit no-known lines, source+license footer, per-drug reference cards. **Seed:** added **Simvastatin**
  so a real **Amlodipine+Simvastatin = Major** flag demos (+ Simvastatin+Vitamin D = Unknown, Amlodipine+Vitamin
  D = none-known). Tests lock the boundary: sourced-only, explicit no-known wording, nothing invented on an empty
  table. ruff + tsc clean, alembic no drift.
- **2026-06-30** — **Log page redesign (surface real intelligence).** Not committed. **Verified live (Playwright,
  0 console errors).** Core insight confirmed: every intake already runs Intake (parse) + Memory (Chroma RAG)
  + Reasoning (obs/alerts) — the UI just hid it. **Backend (minimal, return-existing-data only):**
  (1) `IntakeOut += reasoning_summary` and `intake.py::_run` passes `_get(result,"reasoning_summary")` through
  — the reasoning_node already computed it (newly-created `observations`/`alerts`/`problem`/`suggested_actions`),
  it was just dropped at the route. (2) New `GET /patients/{id}/entries?limit&offset` (`routes/entries.py`,
  `EntryOut` in `clinical_io.py`, registered in `main.py`) — paginated full entry history, read-only.
  **Confirmed `/intake` already returns** `new_entry.structured` (extracted) + `context_bundle.semantic_matches`
  (RAG hits w/ text+date+distance); only reasoning_summary was missing. **Frontend:** Log is now the **landing
  page** (`/` → LogPage, Dashboard → `/dashboard`; AppShell nav reordered). LogPage rewritten as a **chat-style
  thread** from `GET /entries` (user bubble + "Logged: name · attrs"); after a submission it shows **inline**:
  Related-to-past-entries (real `semantic_matches`, dist<1.0, top 2) + New observations/alerts (real
  `reasoning_summary`). Med/report mini-forms **removed**; vital quick-add kept + given per-type contextual
  help (factual ranges, non-diagnostic). Old `IntakeBox.tsx` deleted (dead). **#6 multi-turn clarify:** extended
  to **up to 3 follow-ups** within the EXISTING clarify branch via frontend transcript accumulation + re-parse
  (no GraphState/pipeline change) — verified 2 sequential questions then completion. Caveat (told user): entry
  only persists when parser returns complete; true open-ended stateful dialogue would need LangGraph
  checkpointer+interrupt + a conversation-state model (deferred). ruff + tsc clean, pytest 12 passed.
- **2026-06-30** — **Parts 2 & 3: denser seed + re-verify.** Not committed. **Verified live.**
  **Part 2 — `scripts/seed_demo.py` rewritten** for a high-density ~1-year record (idempotent, same
  `demo@phia.health` login): **74 vital readings** (BP every ~2 wks, weight + **blood_glucose** monthly),
  **20 symptom entries** (migraine now **×12**, increasing cadence; fatigue ×3 clustered; strep ×2 early).
  Arc preserved + **2 new threads**: **lower back pain** (resolved, 3 episodes, alias `back pain`) and
  **elevated blood glucose** (emerging/active, `trend=rising`, evidenced by its own rising glucose series via
  `attributes.vital_types=["blood_glucose"]` — exercises the sub-timeline reading-linkage, NOT symptom
  entries). All 5 problems carry `aliases`/`vital_types`. **Gotcha fixed:** a smooth dense BP ramp made the
  D1 rolling-avg (last-3 vs prior-3) read *stable* (Δ~1%); gave BP a steeper **recent tail** (133→147 / 83→92
  over last 6 readings) so it reads **rising** (sys +5.9%, dia +6.7%) + fires high_bp alerts. Glucose rising
  +8.7%, weight stable. Observations are 6 canned **factual/non-diagnostic** lines (LLM branch dropped from
  seed for determinism); `audit_language` = 0 violations. `ruff` + `pytest` 12 passed.
  **Part 3 — re-verified against the dense data (live + Playwright, 0 console errors):** sub-timelines —
  migraine **13 pts** (12 episodes + trend marker), lower back pain 3 ep + trend + resolved, elevated blood
  glucose **11 reading pts + first_seen**, strep 2 ep + resolved, vitamin D 1 milestone. Dashboard (Tracked
  Problems lists all 5, stat cards/alerts correct), **story** (real LLM, references 12 migraines + BP/glucose
  trends) and **PDF** (valid, 5979 B) all hold up — nothing assumed the old sparse shape. **Note:** re-seed
  changes the patient id (now 6); frontend resolves via `/patients/me` so unaffected.
- **2026-06-30** — **Part 1: Per-problem sub-timeline.** Not committed. **Verified live (current data).**
  New `GET /patients/{id}/problems/{problem_id}/timeline` (`services/problem_timeline.py`, route in
  `routes/timeline.py`, schemas `ProblemTimeline*` in `outputs.py`) assembles ONE problem's chronological
  evidence from PRIMARY data: matched symptom **entries** (linked by normalized `structured.name` ==
  problem name **OR `attributes.aliases`** — needed because the seed named the problem "strep throat" but
  the parsed entry is "sore throat"; added alias to the live strep row), any **vital_readings** for
  vital-linked problems (name→vital_type map + `attributes.vital_types` override), a **derived
  `trend_change`** marker at the 3rd episode (same rule as `problems.upsert`: count≥3→increasing), and
  `first_seen`/`resolved` milestones. **Design decision (per user q):** standalone **observations are NOT
  attached** to the sub-timeline — they're present-tense whole-history syntheses generated "now", so pinning
  them to one dated point would falsely backdate/duplicate (the windowing lesson). The problem's current
  trend/frequency shows in the modal **header** (a fact from the row), not as a dated event. Frontend:
  `ProblemTimelineModal.tsx` (vertical mini-timeline) + clickable **Tracked Problems** card on the dashboard
  + main-timeline "Started tracking X"/"X resolved" points now open the sub-timeline (carry `problemId`).
  Verified: migraine (active, 6 episodes + trend marker at Apr 21) and strep throat (resolved, alias-linked
  "sore throat" entry + "Marked resolved"). ruff + tsc clean, Playwright 0 errors. **(Parts 2 & 3 done — see
  newer entry above.)**
- **2026-06-30** — **Timeline detail windowing fix (per-event-type window).** Not committed. **Verified live.**
  **Bug:** the Timeline detail modal showed empty "What was logged"/"AI Observations" for the *derived trend*
  point ("Blood pressure trending upward"). **Root cause (not the chest-pain entry):** that point anchors to
  the **last** bp_systolic reading (2026-06-27) but represents a ~6-month **span**; querying it with the same
  `window_days=1` as a point event → only 06-26..06-28 → missed the entire producing series. (The chest-pain
  entry id 43 is dated **2026-06-30**, a genuinely *different* day from the trend anchor (06-27) that the
  horizontal UI visually clusters at the "June" end; id 43 correctly lives under the **"Started tracking chest
  pain"** (06-30) point, which already returns it — entries=2, obs=9.) **Fix:** windows are now chosen by event
  TYPE. Detail endpoint gained an optional `?start=YYYY-MM-DD` (asymmetric range `[start, day]`, ignores
  `window_days`); `services/timeline.py::_window_bounds` handles both modes. `Timeline.tsx` tags the trend
  event with `start = first bp reading day` (point events leave `start` undefined → keep narrow ±1d); modal
  subtitle shows the date range for spans. **No schema change, no blanket window bump, no seed change.**
  **Before→after on the broken point:** entries 0→9, vitals 3→17 (full BP series). Regression-checked: First
  BP reading point still vitals=3 (narrow); chest-pain point still shows id 43. ruff + tsc clean, Playwright 0
  errors. (Note: AI-Observations stays empty on the *trend* point by design — observations are generated at
  intake time (06-30) and attach to the 06-30 point, not retroactively to the historical producing span.)
- **2026-06-30** — **Dashboard interactivity pass (3 changes).** Not committed. **Verified live (Playwright,
  demo patient, 0 console errors).**
  **(1) Health Timeline → horizontal + interactive with a REAL detail endpoint.** New backend:
  `GET /api/patients/{id}/timeline/{date}/detail?window_days=1` (`services/timeline.py`,
  `routes/timeline.py`, registered in `main.py`) assembles the FULL context for a date window from the
  canonical tables — `entries` (the patient's **raw_text**, not the parsed summary), `vital_readings`,
  `observations`, `alerts` — scoped to `[date−w, date+w]` in UTC half-open bounds. New schemas
  `TimelineDetailOut` + sub-models in `schemas/outputs.py`. Frontend `Timeline.tsx` rewritten: same
  `buildEvents` placement logic but rendered as a **horizontal scrollable track** of clickable points;
  click opens a **centered modal** (new `Dialog` primitive in `ui.tsx`) that fetches the detail and shows
  4 sections (What was logged / Vitals & symptoms / AI observations / Alerts). Genuinely backend-assembled,
  not re-derived from page data (verified: 2026-01-26 point → real "sore throat with fever" entry text;
  2026-01-01 → 3 vitals).
  **(2) Smaller stat cards + alerts, with hover history + expandable alerts.** `StatCard.tsx` density
  reduced (`p-5→p-3.5`, `text-3xl→text-2xl`) + optional `popover` slot (CSS group-hover, no nav): BP/Weight
  show an inline-SVG **sparkline** (`Sparkline.tsx`, dependency-free) of recent readings from the already-
  fetched vitals; Active Problems/Migraine show a short text popover. **Alerts**: new backend
  `GET /api/patients/{id}/alerts/{aid}/context` (`routes/alerts.py` + `THRESHOLD_DESCRIPTIONS` in
  `services/alerts.py`, schema `AlertContextOut`) returns the last ~5 readings of the alert's `vital_type`
  up to `created_at`, each flagged `breaches`, plus the crossed threshold rule. `AlertsPanel.tsx` rows are
  compact + click-to-expand inline showing those triggering readings (verified: 140/146/144 flagged crossing,
  130/134 not).
  **(3) AI Observations + Suggested Actions promoted above the timeline + show more.** `DashboardPage.tsx`
  reordered: stat cards → alerts → **Observations | Suggested Actions** (2-col) → **Timeline** (full-width,
  bottom). Threaded `obs_limit` through `assemble_state(…, obs_limit=5)` → `build_snapshot` → `?obs_limit`
  query on the snapshot route (**default stays 5** so Story/PDF and the concise-Story fix are untouched);
  dashboard requests `obs_limit=10` (now shows 6 deduped obs vs old cap of 5). Items stay single-line — only
  the count rose. ruff clean, `pytest` 12 passed, `npm run build` (tsc) clean, `alembic check` no drift
  (no schema change). **Env note:** the long-running `:8001 --reload` dev server had silently stopped
  hot-reloading (stale routes → 404s); restarted fresh. **Still pending (next session, unchanged):** Vitals
  individual chart cards + Story "Key Insights" panel.
- **2026-06-30** — **Post-Phase-8 refinement pass (content quality + UX).** Not committed.
  **Story** (`services/story.py`): rewritten to 3 paragraphs (headline → connected reasoning → stable/missing),
  enriched payload (conditions/resolved/missing), whitespace-normalized, still non-diagnostic.
  **Consultation PDF** (`services/pdf_report.py`): redesigned as a real clinical handoff — teal header band,
  **date-range**, **Reason-for-Review** callout (synthesized from rising vitals + increasing problems),
  narrative lead, Active Problems with **frequency/spacing derived from entry dates** (`_problem_pattern`,
  e.g. "6 episodes since Jan 2026, ≈ every 4 wks; more frequent recently"), **Current Medications** table,
  Vital Trends, AI-Surfaced Patterns, **Prompts for Discussion** (suggested actions), Recent Alerts. Color-coded trends.
  **Frontend redesign** (Dashboard milestone): left **sidebar** nav, dashboard **stat cards** + derived
  **Health Timeline** + consistent severity/trend color coding (`lib/tone.ts`, `StatCard`, `Timeline`,
  new `AppShell`), original **teal** palette + typographic hierarchy. New **Medications** + **Reports** pages.
  **Routing bug FIXED:** `/medications` + `/reports` sidebar links fell through the catch-all to Dashboard
  because their routes never existed → added the two pages + routes (+ report list/delete/download endpoints).
  Verified by real click-through.
  **Seed idempotency bug FIXED:** `User.patient` relationship → `passive_deletes=True` so re-running
  `seed_demo` cascades the delete via the DB FK instead of nulling `patients.user_id` (re-seed previously failed).
  **Hallucination grounding — status:** the earlier `"chest heaviness"` observation WAS a genuine fabrication
  (no backing entry) → fixed by tightening the observations prompt (forbid inventing symptoms) + the runtime
  language filter; re-seed produced grounded observations. **Verified honestly on 2026-06-30:** the later
  observation `"Chest pain has been reported once, with a severity of 7"` is **NOT a hallucination** — it is
  grounded in a real entry (id 43, `source=intake`, `attributes.severity=7`) logged via the live intake flow,
  so the observation faithfully reflects actual data. Grounding fix holds.
  **Still pending (next session):** Vitals individual chart cards + Story "Key Insights" panel (queued, not built).
- **2026-06-30** — **Integration & Hardening DONE** (roadmap Phase 8 — final build phase; demo-ready).
  (1) **Resilience** (D13): `groq_client` timeout+retries; `intake.parse_entry` degrades to fallback on Groq
  failure; `/intake` route → clean 502 on pipeline error. (2) **Seed**: `scripts/seed_demo.py` (idempotent)
  → **demo@phia.health / demo-pass-123** (patient "Dana Demo"): 6-month rising BP, migraine increasing (6
  episodes), resolved strep throat, migraine+fatigue cluster, meds, non-diagnostic observations, Chroma
  embeds. (3) **Tests** (D11): `pytest` suite in `backend/tests/` vs separate `phia_test` DB, Groq+vectorstore
  stubbed — units (alerts/trend/BP-recovery/dedupe/guard) + DB services + full-pipeline integration +
  clarify + cross-user 403. **12 passed.** (4) **Non-diagnostic** (D12): tighter prompts + `language_guard.py`
  runtime filter on observations + `scripts/audit_language.py` (seed patient → 0 violations). (5) **Loose ends
  fixed**: `POST /vitals` now recomputes summary + alerts (Phase-5 gap closed, verified 70→68); `/symptoms`
  POST embeds into Chroma; `SECRET_KEY` dev default lengthened (≥32B, silences pyjwt warn); removed unused
  frontend scaffold assets. Verified: ruff clean (app/tests/scripts), `alembic check` no drift, fault-injection
  (Groq down → intake **200** fallback note), Playwright screenshot of seeded dashboard (rich, 0 console errors).
  **NO viva/README/teaching docs (deferred per user).** Not committed (left to user). **System fully built,
  Phases 0–8 complete.**
- **2026-06-30** — **Frontend DONE** (roadmap Phase 7). React+Vite+TS SPA in `frontend/`, talks to the
  REAL backend (Vite proxy `/api`→:8001), no mocks. Auth: JWT in localStorage, axios interceptors
  (attach token / 401→logout), `AuthProvider` resolves user + patient via `/auth/me` + `/patients/me`,
  onboarding if no profile. Pages: Login/Register/Onboarding/Dashboard(snapshot+alerts+ack)/Log(intake
  free-text + clarify + vital/medication/report forms)/Vitals(Recharts: BP dual-line from `vital_readings`
  + trend badges from `vital_summary`)/Story(Groq narrative + **fallback badge** when generated_by=fallback)
  /Share(doctor-access token mint/list/revoke + PDF blob download)/DoctorView(`/shared/:token`, public,
  reuses `SnapshotView`). **2 small backend additions:** `GET /patients/me` (resolve patient id; 404 drives
  onboarding) + CORSMiddleware (`CORS_ORIGINS`). Verified end-to-end with **Playwright + screenshots** for
  every group A–F (login→dashboard, alerts ack 7→6, intake→Logged✓ full pipeline, BP chart rising,
  story prose, share→doctor-view shows same data + PDF); 0 console errors; `npm run build` (tsc) clean.
  Backend now 33 routes. Not committed (left to user). Frontend `.env`/`node_modules`/`dist` gitignored.
  **All 7 build phases complete; next: Phase 8 (integration/hardening/demo prep).**
  Note: intake UI calls take ~10-20s (full Groq pipeline) — fine, button shows "Sending…".
- **2026-06-30** — **Response + Outputs DONE** (roadmap Phase 6). Backbone:
  `app/services/state_assembler.py::assemble_state()` (one assembled `PatientHealthState` from Postgres)
  — snapshot, story, PDF, and `/shared/*` ALL read it, so they can't drift. `dedupe_observations`
  (Jaccard ≥0.6, cap 5) + `derive_recent_changes` live here and feed snapshot AND story. Built:
  `services/{snapshot,story,pdf_report}.py`; routes `outputs.py` (snapshot/story/consultation-pdf/problems/
  observations), `alerts.py` (list + ack), `doctor_access.py` (mint/list/revoke tokens),
  `shared.py` (token-gated `/shared/{token}/snapshot|story|consultation/pdf`); `deps.get_patient_by_token`.
  Story = Groq `RESPONSE_MODEL` with deterministic fallback (forced-outage test → `generated_by:fallback`,
  still 200). Snapshot + PDF are LLM-free. `vitals/summary` added to vitals.py *before* `/{vital_id}` to
  avoid path collision. `response_node` stays a stub (outputs are on-demand REST, matching the diagram).
  **Verified (carol, pid 2, real Groq):** snapshot obs deduped 28→5; recent_changes show BP +17%/+14%;
  story flows as prose (not repetitive); PDF `%PDF-1.4` 3119B; alert ack flips; doctor `/shared` snapshot
  **byte-identical** to patient snapshot; invalid/revoked token → 403. ruff clean; alembic no drift
  (no schema change). New dep: reportlab. **D8 caveat resolved:** Groq narrative quality is adequate —
  no provider swap needed. Not committed (left to user). **Backend feature-complete; next: Phase 7 frontend.**
  Minor: dedup still lets ~2 near-dupes through at 0.6 threshold — could lower if needed (cap is 5 anyway).
  Route-registration note: `create_app()` includes all routers **unconditionally** (no env/state gating; no
  circular import) and uvicorn serves all 32 routes (verified by live 200s) — a transient `len(app.routes)==4`
  seen only via throwaway `python -c` imports was a module-state measurement artifact, never the real runtime.
- **2026-06-30** — **Reasoning Engine DONE** (roadmap Phase 5). `reasoning_node` now real; services in
  `app/services/{vitals_trend,alerts,problems,clusters,missing_info,observations}.py`. Implements:
  vital extraction→`vital_readings`→rolling-avg `vital_summary` (D1); threshold `alerts` (OQ2);
  active/resolved `problems` (match→episode_count++/trend, new→create, auto-resolve >90d=OQ3);
  `symptom_clusters` (48h window=OQ5); `missing_information` + `suggested_actions` (gap rules, dedup);
  LLM `observations` (Groq REASONING_MODEL, strictly non-diagnostic, skipped if no key). Reasoning owns
  `vital_readings`+`vital_summary` for the graph path (entries[type=vital]→readings; reads ALL readings of
  a type so CRUD vitals are included). Verified via `/intake` (real Groq): BP trend rising (5 readings),
  headache episode_count=3/increasing, headache+nausea cluster, high_bp alerts, auto-resolve of a 120-day-old
  problem, non-diagnostic observations, missing-BP gap + suggested action. **Bug found & fixed:** Groq
  inconsistently parsed BP — sometimes only systolic in `value`, diastolic dropped; hardened intake prompt
  (BP→always systolic+diastolic in attributes) AND `extract_readings` (regex-recovers both numbers from
  raw_text, never emits a junk `blood_pressure` series). No schema change/migration. Not committed (left to
  user). Next: Phase 6 (Response + outputs) — also re-evaluate Response narrative quality (D8 caveat).
  Note: observations accumulate ~1-3 per run and can get repetitive — consider dedup/limit in Phase 6.
- **2026-06-30** — **LangGraph pipeline + Memory DONE** (roadmap Phase 4). First AI/vector work.
  **Chroma:** `app/vectorstore/collections.py` bootstraps both collections (`patient_entries`,
  `patient_reports`) with DefaultEmbeddingFunction (all-MiniLM-L6-v2 ONNX); metadata schemas verified to
  match §5; warmed in `main.py` lifespan. **Graph:** `app/graph/{state,graph}.py` + `nodes/` — StateGraph
  `START→intake→(clarify|memory)→reasoning→response→END` (reasoning/response are pass-through stubs).
  **Intake** (`nodes/intake.py`): parse via Groq (`app/core/llm.py`, openai client → GROQ_BASE_URL,
  JSON mode); on `complete` writes `entries` row + `patient_entries` embedding + sets `new_entry`;
  on incomplete routes to clarify (writes nothing). Swappable `parse_entry` with a deterministic fallback
  when `GROQ_API_KEY` unset. **Memory** (`nodes/memory.py`): Chroma top-k=5 (self-excluded via `entry_id $ne`)
  + bounded Postgres (active problems, vital_summary, active meds, entries < RECENT_WINDOW_DAYS) →
  `context_bundle`; writes `memory_log` audit. **Endpoints:** `POST /patients/{id}/intake` +
  `/intake/answer` (clarify resume = **stateless re-invoke**, recombines text). **Verified** (fallback
  parser, no key yet): intake→entries+chroma+memory_log, semantic retrieval w/ self-exclusion (dist 0.53),
  clarify routes & writes nothing, cross-user 403, ruff clean. **PENDING user's `GROQ_API_KEY`** to verify
  real LLM parsing + LLM-authored clarify questions. New deps: langgraph, openai. Not committed (left to user).
  Next: Phase 5 (Reasoning Engine) — also resolve OQ7 (Reasoning/Response LLM).
- **2026-06-29** — **Auth & Core CRUD DONE** (roadmap Phase 3, persistence only — no LangGraph/AI).
  Built + verified one group at a time (real request→DB→response):
  **A) Auth** — `core/security.py` (bcrypt hashing + pyjwt HS256), `api/deps.py`
  (`get_current_user`, `get_owned_patient`/`OwnedPatient` ownership guard), `routes/auth.py`
  (register 201/409, login OAuth2-form→JWT, `/me`). **B) Patient** — `routes/patients.py`
  (POST/GET/PUT, dup profile→409) + `routes/background.py` (GET/PUT upsert `medical_background`,
  `/history` alias via stacked decorators). **C) Clinical** — `medications` (full CRUD),
  `vitals`→`vital_readings` (POST auto `recorded_at`/GET/DELETE), `symptoms`→`entries(type='symptom')`
  (POST/GET/DELETE, **no PUT**, returns 405). **D) Reports** — `routes/reports.py` multipart upload
  → file saved to `UPLOAD_DIR/<patient>/<uuid>_<name>` + row; GET list/one, `/file` download, DELETE
  removes row+file. DTOs in `app/schemas/{auth,patient,clinical_io,report}.py` (`from_attributes=True`).
  Error conventions confirmed: 404 not-found vs 403 not-owned (cross-user tested), 409 conflict.
  New deps: bcrypt, pyjwt, python-multipart, email-validator. New config: SECRET_KEY, JWT_ALGORITHM,
  ACCESS_TOKEN_EXPIRE_MINUTES, UPLOAD_DIR. `uploads/` gitignored. 17 API paths live; ruff clean;
  `alembic check` = no drift (symptoms/reports reuse existing tables). **Not committed** (left to user).
  Next: Phase 4 (LangGraph pipeline + Memory).
- **2026-06-29** — **Data Layer & Schema DONE** (roadmap Phase 2). Wrote SQLAlchemy 2.0 models for all
  16 tables under `app/models/` (grouped: `user, patient, clinical, intelligence, records, access` +
  `mixins.py` with `CreatedAtMixin`/`TimestampMixin`); `app/models/__init__.py` imports all (Alembic
  picks them up). Built Pydantic `PatientHealthState` + sub-models in `app/schemas/{enums,health_state}.py`
  (LangGraph state, validates empty). Conventions: integer BigInteger PKs, `patient_id` FK `ondelete=CASCADE`,
  string enums (not native PG enums), hybrid JSONB `attributes`. `problems` = single status-discriminated
  table (CHECK `active|managed|resolved`, composite index `ix_problems_patient_status`). Generated +
  applied first migration `b7b529cb8dea_initial_schema`. Verified: 16 tables live in Postgres,
  `\d problems` shows status/check/index, `alembic check` → "No new upgrade operations" (no model↔DB drift),
  ruff clean. Fixed one bug pre-migration: column named `text` shadowed `sqlalchemy.text` in
  `intelligence.py` → aliased import to `sa_text`. Not committed (left to user). Next: Phase 3 (Auth & CRUD).
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

- **OQ7 — RESOLVED 2026-06-30 (D8):** Reasoning + Response use Groq `llama-3.3-70b-versatile`. Response
  narrative quality to be re-evaluated in Phase 6 (swap only if it disappoints).
- **OQ1 (pre Phase 4):** Two-tier retrieval (recent verbatim + pre-summarized older history) is a
  future upgrade over D2's bounded pull. Only build if context size becomes a real problem.
- **OQ2 — RESOLVED 2026-06-30:** alert thresholds defined (see "Reasoning constants" in §2 / `ALERT_THRESHOLDS`).
- **OQ3 — RESOLVED 2026-06-30:** auto-resolve window = 90 days (`RESOLVE_AFTER_DAYS`).
- **OQ4 — RESOLVED 2026-06-29:** Doctor access = patient-issued, time-limited read tokens
  (`doctor_access` table, default 7-day expiry, revocable). Doctor visits `/shared/{token}/...`,
  gets READ-ONLY access to snapshot/story/PDF only — never CRUD/writes/raw data. No doctor login.
- **OQ5 — RESOLVED 2026-06-30:** symptom-cluster window = 48h, min 2 distinct (`CLUSTER_WINDOW_HOURS`).
- **OQ6 — v2 status 2026-11-27:** model names come from the owner's LiteLLM proxy (defaults `claude-haiku-5-5` / `claude-sonnet-5-5`, unverified until `scripts.llm_smoke_test --list-models` runs with keys). Original note:
  Confirm Claude model IDs + embedding model availability against `claude-api`
  skill before first LLM/embedding call.
