# Scripts

Helper scripts for local development of the CONNECT.PH Clinic Platform. These are convenience wrappers, not required — any step they perform can also be run manually (see the root [`README.md`](../README.md) quickstart).

## `setup-dev.ps1` / `setup-dev.sh`

Bootstraps a fresh local dev environment in one pass:

1. Copies `frontend/.env.example` → `frontend/.env.local` and `backend/.env.example` → `backend/.env` (only if the target doesn't already exist — never overwrites your existing config).
2. Starts the local Postgres + Redis containers via `docker/docker-compose.yml`.
3. Creates a Python virtualenv in `backend/.venv` and installs backend dependencies.
4. Runs `npm install` for the frontend.
5. Runs Alembic migrations (`alembic upgrade head`) and seeds foundational data (roles/permissions), if a seed script is present.

### Usage

**Windows (PowerShell):**

```powershell
./scripts/setup-dev.ps1
```

**macOS / Linux / WSL / Git Bash:**

```bash
bash scripts/setup-dev.sh
```

Both scripts are idempotent — safe to re-run after pulling new changes (they won't clobber an existing `.env`/`.env.local`, and `alembic upgrade head` only applies pending migrations).

### Prerequisites

- Docker Desktop (for the Postgres/Redis containers) — or point `backend/.env`'s `DATABASE_URL` at an existing Supabase project instead and skip the Docker step.
- Python 3.12+ on `PATH`.
- Node.js 20+ and npm on `PATH`.

## Adding new scripts

Keep scripts focused (one clear purpose each) and cross-platform where practical — provide both a `.ps1` and a `.sh` variant if the task is something Windows and non-Windows contributors will both need (as with `setup-dev`). Document any new script in this file.
