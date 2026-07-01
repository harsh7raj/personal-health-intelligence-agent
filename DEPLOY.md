# Deploying (free tier)

This app has **two parts** that get hosted separately:

| Part | Host | Cost |
|------|------|------|
| `frontend/` (React/Vite) | **Vercel** | Free |
| `backend/` (FastAPI) | **Render** | Free |
| PostgreSQL database | **Neon** | Free |
| ChromaDB vector store | runs *inside* the backend (embedded) | Free |
| Groq LLM | you already have a key | Free tier |

Chroma runs embedded (in-process) in production, so there is **no separate vector-DB
server to host**. The config files are already in the repo:
`render.yaml` (repo root), `backend/start.sh`, `frontend/vercel.json`.

> **Do the steps in this order.** Each step produces a URL or key the next step needs.

---

## 1. Database — Neon (Postgres)

1. Sign up at <https://neon.tech> with GitHub.
2. Create a project (any name). Pick a region near you.
3. Open **Connection string** and copy it. It looks like:
   `postgresql://user:pass@ep-xxx.aws.neon.tech/dbname?sslmode=require`
4. **Rewrite the scheme** for this app's driver — change `postgresql://` to
   `postgresql+psycopg://`, keep everything else (including `?sslmode=require`):
   `postgresql+psycopg://user:pass@ep-xxx.aws.neon.tech/dbname?sslmode=require`
5. Save this string — it's your `DATABASE_URL`.

---

## 2. Backend — Render

1. Sign up at <https://render.com> with GitHub.
2. **New +  →  Blueprint**. Select this repo. Render reads `backend/render.yaml`
   and proposes the `phia-backend` service. Approve it.
   *(The blueprint file must live at the repo root — it does; the service itself
   still builds from the `backend/` folder via `rootDir`.)*
3. Before the first deploy finishes, open the service's **Environment** tab and set:
   - `DATABASE_URL` → the Neon string from step 1 (the `postgresql+psycopg://` one)
   - `GROQ_API_KEY` → your Groq key
   - `CORS_ORIGINS` → leave blank for now; you'll fill it in step 4
   - (`SECRET_KEY` is auto-generated; `CHROMA_MODE`, `SEED_ON_START` are preset.)
4. Deploy. First boot runs migrations and seeds the demo data, so it takes a few minutes.
   When it's live, copy the URL, e.g. `https://phia-backend.onrender.com`.
5. Sanity check: open `https://phia-backend.onrender.com/api/health` — expect
   `{"status":"ok", ...}`.

---

## 3. Frontend — Vercel

1. Sign up at <https://vercel.com> with GitHub.
2. **Add New  →  Project**, import this repo.
3. Set **Root Directory** to `frontend`. Framework preset auto-detects as **Vite**.
4. Under **Environment Variables** add:
   - `VITE_API_BASE` → your Render URL **plus `/api`**, e.g.
     `https://phia-backend.onrender.com/api`
5. **Deploy.** When done, copy the Vercel URL, e.g. `https://your-app.vercel.app`.

---

## 4. Connect them (CORS)

1. Back in **Render → Environment**, set:
   - `CORS_ORIGINS` → your Vercel URL, e.g. `https://your-app.vercel.app`
     (no trailing slash; comma-separate if you have more than one).
2. Render redeploys automatically. Once it's back up, open your Vercel URL — the app
   should load and talk to the backend.

**Demo login:** `demo@phia.health` / `demo-pass-123`

---

## Free-tier trade-offs (worth knowing)

- **Cold starts.** Render's free backend sleeps after ~15 min idle. The next request
  wakes it, which takes ~50s. Normal for free hosting.
- **Vector store resets on restart.** Chroma is embedded on Render's ephemeral disk, so
  it's rebuilt on every restart. `SEED_ON_START=true` re-seeds a consistent demo dataset
  each boot — great for a portfolio demo, but user-added data won't survive a restart.
  Your **Neon Postgres data persists** regardless.
- **Want real persistence?** Set `SEED_ON_START=false` after the first successful deploy,
  and move Chroma to a persistent host (Chroma Cloud free tier) by setting
  `CHROMA_MODE=http` + `CHROMA_HOST`/`CHROMA_PORT` to that server.

## Updating the app

Push to `main`. Vercel and Render both auto-deploy from GitHub on every push.
