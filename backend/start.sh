#!/usr/bin/env bash
# Render start command for the FastAPI backend.
# Runs DB migrations, optionally (re)seeds the demo dataset, then serves the app.
set -euo pipefail

echo "==> Applying database migrations"
uv run alembic upgrade head

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "==> Seeding demo dataset (SEED_ON_START=true)"
  uv run python -m scripts.seed_demo
fi

echo "==> Starting uvicorn on port ${PORT:-8000}"
exec uv run uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
