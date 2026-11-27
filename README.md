# Personal Health Intelligence Agent

A **Health Intelligence Engine** that maintains a *longitudinal* view of a patient's health —
it **observes and explains** history over months and years, rather than acting as a passive
health record. Every new input (symptom, vital, medication, lab report) flows through a
controlled multi-agent pipeline that updates a shared **`PatientHealthState`** and produces
immediate, human-readable insights, trends, and summaries.

> ⚕️ **This is not an AI doctor.** It never diagnoses, predicts, or prescribes. Every AI
> output is phrased as a data-derived *observation* or *pattern*, never medical advice.

<!-- Live demo:  Frontend → <your-vercel-url>   ·   API → <your-render-url>/api/health -->

---

## Why

Most health apps are just data stores — they let you log things but never *reason* about them
over time. That pushes the burden of continuity onto people:

- **Patients** have to remember their own timelines, trends, and gaps.
- **Doctors** spend consultation time reconstructing history ("When did this start? What have
  you tried?") instead of focusing on the problem.

This project solves for **health continuity**: preserving and connecting longitudinal context
so every encounter starts with rich, integrated information.

## What it does

- **Longitudinal patient state** — active problems, resolved problems, vital summaries,
  medications, and medical background maintained as one evolving picture.
- **Trend detection** on vitals (BP, weight, heart rate, glucose, SpO₂) via an explainable
  rolling-average delta — `rising` / `falling` / `stable`, no black-box ML.
- **Symptom clustering** — surfaces groups of symptoms that recur together.
- **AI observations** — data-grounded notes ("fatigue often follows headache episodes"),
  passed through a language guard so nothing reads as a diagnosis.
- **Report intelligence** — uploaded lab PDFs are parsed into findings, trends, and an
  AI summary that the agent can reason over.
- **Missing-info & next-action cues** — e.g. "no blood pressure reading in 60 days."
- **Doctor handoff** — a deterministic, ReportLab-generated consultation PDF and shareable
  read-only doctor view.

## Architecture

A **LangGraph** sequential multi-agent pipeline (deterministic orchestration — the next step
is fixed by design, not chosen by an LLM at runtime). Four focused agents pass a shared
`PatientHealthState` between them:

| Agent | Single responsibility |
|-------|-----------------------|
| **Intake** | Parse free-text / uploads into structured, normalized entries |
| **Memory** | Retrieve only the relevant history (Postgres facts + Chroma semantic search) |
| **Reasoning** | Update the state — detect trends, cluster symptoms, form observations |
| **Response** | Format outputs — health snapshot, narrative story, consultation PDF |

Narrow responsibilities keep each part testable and reduce hallucination.

## Tech stack

**Backend** — Python 3.11 · FastAPI · LangGraph · Pydantic v2 · PostgreSQL (SQLAlchemy 2 +
Alembic) · ChromaDB (local `all-MiniLM-L6-v2` embeddings) · Groq LLM (OpenAI-compatible) ·
JWT auth · ReportLab (PDF)

**Frontend** — React 19 · Vite · TypeScript · Tailwind CSS · TanStack Query · axios ·
React Router · Recharts

**Infra** — Postgres via docker-compose (or a portable install) · embedded Chroma · `uv` for backend packaging

## Repository layout

```
backend/     FastAPI app, LangGraph pipeline, models, migrations, seed scripts
frontend/    React + Vite single-page app
Docs/        Design document (master spec + architecture diagram)
DEPLOY.md    Free-tier deployment walkthrough (Vercel + Render + Neon)
```

## Run it locally

**Prerequisites:** Python 3.11, [`uv`](https://docs.astral.sh/uv/), Node 20+, and Postgres 16
(Docker, or the portable no-admin install below). Chroma runs embedded inside the backend.
LLM keys are optional: without them the app runs with offline fallbacks (see `backend/.env.example`).

**One command** (from `backend/`):

```bash
cp .env.example .env            # PowerShell: Copy-Item .env.example .env
uv run python -m scripts.dev
```

It starts Postgres if needed (Docker, or `LOCAL_PG_HOME` below), creates the database, applies
migrations, seeds the demo patient if missing, then serves:
- API: http://localhost:8001 (health check at `/api/health`)
- Web app: http://localhost:5173 (the Vite proxy sends `/api` to port 8001)

Ctrl+C stops both servers; Postgres keeps running. Add `--reload` to restart the API on code changes.

**Demo login:** `demo@phia.health` / `demo-pass-123`

### Windows without Docker (portable Postgres, no admin rights)

1. Download the PostgreSQL 16 "binaries" zip for Windows x64 from
   https://www.enterprisedb.com/download-postgresql-binaries and unzip it to
   `%LOCALAPPDATA%\phia-postgres` (you only need `pgsql\bin`, `lib` and `share`; skip pgAdmin).
2. Create the data folder once (user and password `phia`):
   ```powershell
   $pg = "$env:LOCALAPPDATA\phia-postgres"
   Set-Content "$pg\pw.tmp" "phia" -NoNewline
   & "$pg\pgsql\bin\initdb.exe" -D "$pg\data" -U phia --pwfile="$pg\pw.tmp" -E UTF8 --locale=C --auth=scram-sha-256
   Remove-Item "$pg\pw.tmp"
   ```
3. In `backend/.env`, set `LOCAL_PG_HOME=C:\Users\<you>\AppData\Local\phia-postgres`.
   `scripts.dev` then starts it for you; `uv run python -m scripts.dev --stop-db` stops it.

### Step by step (what the one command does)

```bash
cd backend
docker compose up -d                    # or start the portable Postgres
uv run alembic upgrade head
uv run python -m scripts.seed_demo      # with the API stopped: embedded Chroma allows one writer
uv run uvicorn app.main:app --port 8001
cd ../frontend && npm ci && npm run dev
```

### Checks

```bash
cd backend
uv run ruff check .
uv run pytest          # needs Postgres; uses a separate phia_test database
uv run alembic check
cd ../frontend && npm run build
```

## Deployment

A complete, beginner-friendly free-tier deploy guide (frontend → Vercel, backend → Render,
database → Neon) lives in **[DEPLOY.md](./DEPLOY.md)**.

## Status

A B.E. capstone project — functional end to end, but a work in progress, not a finished
product. Expect ongoing changes and refinements.

## Disclaimer

For educational and informational purposes only. It does **not** provide medical advice,
diagnosis, or treatment. Always consult a qualified healthcare professional.
