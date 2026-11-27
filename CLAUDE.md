# CLAUDE.md: Personal Health Intelligence Agent (v2)

B.E. capstone. FastAPI + LangGraph + PostgreSQL + Chroma backend in `backend/`,
React + Vite + TypeScript frontend in `frontend/`.

## Read first, in this order
1. `ROADMAP.md`: the v2 plan (10 phases with checkboxes). This is the task list.
2. `memory.md`: design decisions, schema, endpoints, pipeline, work log. This is the decision log.
3. `README.md`, then the code: `backend/app`, `backend/scripts`, `backend/tests`, `frontend/src`.

## Ground rules (non-negotiable, from ROADMAP.md)
- **Observe, never diagnose.** No diagnoses, causes, or treatment advice from the AI.
- **Code finds the pattern, the LLM only phrases it.** Retrieval, counting, date matching and
  safety thresholds are Python. The LLM only words what it is handed.
- **Every AI claim cites its evidence** (dated entries, report values, quoted label text).
- **The doctor's words are labeled as the doctor's.** The app relays instructions; it never invents its own.
- **Medicines: the AI can raise a concern but never gives the all-clear.** Never call a combination "safe".
  Every medication finding states its source: Verified (database), Official label (quoted), or AI flag (unverified).
- **Nothing medical is saved without the user confirming it** (visit notes, medicine changes, brand-to-generic matches).
- **Runs locally with one command, and still works if LiteLLM is down** (Groq fallback).

## How to work
- Work on the `v2` branch, one phase at a time, following ROADMAP.md's "Suggested order" unless told otherwise.
  One commit per task, with a clear message. `main` stays the demo-able v1 (as on GitHub); v2 lands via a PR.
- **GitHub:** `origin` is the owner's personal repo `harsh7raj/personal-health-intelligence-agent` (public).
  Push only when the owner asks, only to `origin`, and only as `harsh7raj`: a repo-local credential helper
  fetches that account's token from `gh`, so never change it or push with any other GitHub account.
- Keep the app runnable at the end of every phase. Minimal, focused changes; don't rewrite things that work.
- After each task, run what's relevant and don't move on with failures:
  - backend (in `backend/`): `uv run ruff check .`, `uv run pytest`, `uv run alembic check`
  - frontend (in `frontend/`): `npm run build`
- Add tests for new logic. **Tests never call a real LLM or external API**; stub them (see `backend/tests/conftest.py`).
- Database changes only through Alembic migrations.
- Every LLM call goes through `app/core/llm.py`, with the model chosen per task from config.
  No direct LLM client calls anywhere else.
- Never commit secrets. Keep `backend/.env.example` up to date.
- ROADMAP.md was written from reading the code, not running it. If it doesn't match the code: verify,
  tell the owner, and propose a fix instead of guessing.
- Ask before making product or safety decisions the roadmap doesn't cover.
- Tick ROADMAP.md checkboxes as tasks are done. Log new decisions in memory.md (D15 onward) and add a
  Work Log entry at the end of each session.
- Explain any new dependency before adding it. Prefer the existing stack: uv, FastAPI, SQLAlchemy 2,
  Alembic, LangGraph, React 19, TanStack Query, Tailwind, Recharts.
- Local demo only: no deployment work (`DEPLOY.md` / `render.yaml` are legacy v1 docs).
- Keep LLM spend low: stub LLMs in tests, make real calls only when needed to verify something,
  and cache anything generated for the demo.

## Environment
- Backend on port 8001, frontend on 5173; the Vite proxy sends `/api` to 8001.
- Postgres 16 on localhost:5432 (user/password `phia`): `docker compose up -d` in `backend/`, or the
  portable no-admin install on the owner's Windows machine (see README). Chroma runs embedded locally.
- Tests use a separate `phia_test` database, created and dropped by `backend/tests/conftest.py`.
- LLM calls go through the owner's LiteLLM proxy (`LLM_BASE_URL`, `LLM_API_KEY` in `backend/.env`):
  Haiku for small jobs, Sonnet for important ones (model plan in ROADMAP.md). Exact model names come
  from `GET {LLM_BASE_URL}/v1/models`. A Groq key (`FALLBACK_API_KEY`) covers the fallback and Whisper.
- The owner develops on Windows (PowerShell / Git Bash); teammates may use macOS. Keep scripts cross-platform.
