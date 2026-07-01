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

**Infra** — docker-compose (Postgres + Chroma) for local dev · `uv` for backend packaging

## Repository layout

```
backend/     FastAPI app, LangGraph pipeline, models, migrations, seed scripts
frontend/    React + Vite single-page app
Docs/        Design document (master spec + architecture diagram)
DEPLOY.md    Free-tier deployment walkthrough (Vercel + Render + Neon)
```

## Run it locally

**Prerequisites:** Docker, Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Node 20+, and a
[Groq API key](https://console.groq.com/) (free).

```bash
# 1. Backend infra (Postgres + Chroma)
cd backend
docker compose up -d

# 2. Backend env + deps
cp .env.example .env        # then paste your GROQ_API_KEY into .env
uv sync

# 3. Migrate + seed the demo dataset
uv run alembic upgrade head
uv run python -m scripts.seed_demo

# 4. Run the API  (http://localhost:8000)
uv run uvicorn app.main:app --reload

# 5. Frontend  (in a second terminal → http://localhost:5173)
cd ../frontend
npm install
npm run dev
```

**Demo login:** `demo@phia.health` / `demo-pass-123`

## Deployment

A complete, beginner-friendly free-tier deploy guide (frontend → Vercel, backend → Render,
database → Neon) lives in **[DEPLOY.md](./DEPLOY.md)**.

## Status

A B.E. capstone project — functional end to end, but a work in progress, not a finished
product. Expect ongoing changes and refinements.

## Disclaimer

For educational and informational purposes only. It does **not** provide medical advice,
diagnosis, or treatment. Always consult a qualified healthcare professional.
