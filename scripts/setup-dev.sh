#!/usr/bin/env bash
#
# Bootstraps a local development environment for the CONNECT.PH Clinic
# Platform (macOS/Linux/WSL/Git Bash). Windows users can use
# scripts/setup-dev.ps1 instead.
#
# Copies environment file templates, installs frontend and backend
# dependencies, runs database migrations, and seeds foundational data
# (roles/permissions). Assumes Docker is running for local Postgres/Redis,
# or that backend/.env is already pointed at a Supabase project.
#
# Usage:
#   bash scripts/setup-dev.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> CONNECT.PH Clinic Platform — local dev setup"

# ---------------------------------------------------------------------------
# 1. Environment files
# ---------------------------------------------------------------------------
echo
echo "[1/5] Copying environment file templates..."

copy_env() {
  local example="$1" target="$2"
  if [ ! -f "$REPO_ROOT/$example" ]; then
    echo "  ! Skipping: $example not found yet."
    return
  fi
  if [ -f "$REPO_ROOT/$target" ]; then
    echo "  - $target already exists, leaving it untouched."
  else
    cp "$REPO_ROOT/$example" "$REPO_ROOT/$target"
    echo "  + Created $target from $example"
    echo "    -> Edit it now and fill in real values (DB, JWT secret, Supabase keys, etc.)."
  fi
}

copy_env "frontend/.env.example" "frontend/.env.local"
copy_env "backend/.env.example" "backend/.env"

# ---------------------------------------------------------------------------
# 2. Start infra (Postgres + Redis) via Docker Compose
# ---------------------------------------------------------------------------
echo
echo "[2/5] Starting Postgres + Redis via Docker Compose..."
if command -v docker >/dev/null 2>&1; then
  docker compose -f "$REPO_ROOT/docker/docker-compose.yml" up -d postgres redis \
    && echo "  + Postgres and Redis containers are starting." \
    || echo "  ! Failed to start containers — is Docker running?"
else
  echo "  ! Docker not found on PATH — start Postgres/Redis manually or install Docker."
fi

# ---------------------------------------------------------------------------
# 3. Backend: virtualenv + dependencies
# ---------------------------------------------------------------------------
echo
echo "[3/5] Setting up backend (Python) environment..."
cd "$REPO_ROOT/backend"

if [ ! -d ".venv" ]; then
  echo "  Creating virtualenv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip
if [ -f "pyproject.toml" ]; then
  pip install -e ".[dev]"
elif [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
else
  echo "  ! No pyproject.toml or requirements.txt found yet — skipping install."
fi
echo "  + Backend dependencies installed."

# ---------------------------------------------------------------------------
# 4. Frontend: npm install
# ---------------------------------------------------------------------------
echo
echo "[4/5] Installing frontend (npm) dependencies..."
cd "$REPO_ROOT/frontend"
if [ -f "package.json" ]; then
  npm install
  echo "  + Frontend dependencies installed."
else
  echo "  ! frontend/package.json not found — skipping npm install."
fi

# ---------------------------------------------------------------------------
# 5. Database migrations + seed data
# ---------------------------------------------------------------------------
echo
echo "[5/5] Running database migrations and seed data..."
cd "$REPO_ROOT/backend"
source .venv/bin/activate

echo "  Waiting a few seconds for Postgres container to be ready..."
sleep 5

if alembic upgrade head; then
  echo "  + Migrations applied."
else
  echo "  ! Migration failed. Check backend/.env DATABASE_URL and that Postgres is reachable."
fi

if [ -f "app/db/seed.py" ]; then
  python -m app.db.seed && echo "  + Seed data (roles, permissions) applied."
else
  echo "  ! app/db/seed.py not found yet — skipping seed step. Seed roles/permissions manually."
fi

echo
echo "==> Setup complete."
echo "Next steps:"
echo "  Backend:  cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000"
echo "  Frontend: cd frontend && npm run dev"
echo "  Docs:     http://localhost:8000/docs   |   App: http://localhost:3000"
