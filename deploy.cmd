@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  CONNECT.PH Clinic Platform - Production Deployment (Phase 3)
REM
REM  Run this on the clinic Server PC, from the repo root, after
REM  new commits have landed on origin/main. It:
REM    1. Refuses to run if the repo-root .env is missing (required
REM       for Compose variable substitution - POSTGRES_PASSWORD,
REM       CLINIC_API_BASE_URL, CLINIC_FRONTEND_ORIGIN).
REM    2. Refuses to run if the checkout has uncommitted local changes.
REM    3. Pulls the latest code with `git pull --ff-only` (never merges).
REM    4. Validates the full production Compose configuration
REM       (`docker compose --env-file .env ... config`) before touching
REM       anything - catches a missing/incomplete .env or a broken
REM       compose file before any build/restart happens.
REM    5. Builds only the backend/frontend images (docker/docker-compose.prod.yml).
REM    6. Restarts only backend/frontend - postgres and redis are left
REM       running untouched, their data volumes are never touched.
REM    7. Shows `docker compose ps`.
REM    8. Runs basic HTTP health checks and reports success/failure.
REM
REM  Deliberately does NOT:
REM    - run `git reset --hard`, or any destructive git command
REM    - run `docker compose down` or `down -v` (never deletes volumes)
REM    - touch postgres or redis at all
REM    - run Alembic migrations (see docker-compose.prod.yml's backend
REM      command override - migrations are a separate, manual step)
REM    - discover or edit the Server PC's IP - that's the operator's job,
REM      via the root .env's CLINIC_API_BASE_URL/CLINIC_FRONTEND_ORIGIN
REM      (see .env.example)
REM    - automatically roll back on a failed health check - it reports
REM      the failure and stops, so an operator can inspect logs before
REM      deciding what to do next
REM ============================================================

cd /d "%~dp0"

set COMPOSE_FILES=-f docker\docker-compose.yml -f docker\docker-compose.prod.yml
set ENV_FILE=--env-file .env

echo ============================================================
echo  CONNECT.PH Clinic Platform - Production Deployment
echo ============================================================
echo.

REM --- 1. Refuse to deploy without the clinic .env ------------------------
echo [1/8] Checking for the clinic .env...
if not exist ".env" (
    echo.
    echo FAILED: no ".env" file found in the repo root.
    echo.
    echo This file is required - it supplies POSTGRES_PASSWORD (Compose
    echo variable substitution needs it to even parse the production
    echo config^), and CLINIC_API_BASE_URL / CLINIC_FRONTEND_ORIGIN (the
    echo clinic Server PC's actual LAN address for this site^).
    echo.
    echo To fix: copy .env.example to .env in the repo root and fill in
    echo the real values for this clinic - see .env.example for exactly
    echo which variables are needed and what they mean.
    echo.
    echo Nothing was pulled, validated, built, or restarted.
    exit /b 1
)
echo   OK - .env found.
echo.

REM --- 2. Refuse to deploy over uncommitted local changes -----------------
echo [2/8] Checking for uncommitted local changes...
set DIRTY=
for /f "delims=" %%L in ('git status --porcelain 2^>^&1') do set DIRTY=1
if defined DIRTY (
    echo.
    echo FAILED: this checkout has uncommitted local changes.
    echo Resolve or discard them before deploying - showing status below:
    echo.
    git status --short
    echo.
    echo Nothing was pulled, validated, built, or restarted.
    exit /b 1
)
echo   OK - working tree clean.
echo.

REM --- 3. Pull latest code (fast-forward only) -----------------------------
echo [3/8] Pulling latest code (git pull --ff-only)...
git pull --ff-only
if errorlevel 1 (
    echo.
    echo FAILED: git pull --ff-only did not succeed - local and origin/main
    echo have diverged, or the remote is unreachable. Resolve manually
    echo ^(this script will never merge or force-overwrite^).
    echo Nothing was validated, built, or restarted.
    exit /b 1
)
echo.

REM --- 4. Validate the production Compose configuration --------------------
echo [4/8] Validating production Compose configuration...
docker compose %ENV_FILE% %COMPOSE_FILES% config
if errorlevel 1 (
    echo.
    echo FAILED: the production Compose configuration is invalid, or
    echo .env is missing a required value ^(e.g. POSTGRES_PASSWORD^).
    echo See the Compose output above for the exact error.
    echo.
    echo Nothing was built or restarted.
    exit /b 1
)
echo   OK - Compose configuration is valid.
echo.

REM --- 5. Build application images only -------------------------------------
echo [5/8] Building backend and frontend images...
docker compose %ENV_FILE% %COMPOSE_FILES% build backend frontend
if errorlevel 1 (
    echo.
    echo FAILED: docker compose build failed. Previous containers are
    echo still running, untouched - nothing has been restarted.
    exit /b 1
)
echo.

REM --- 6. Restart/recreate only backend + frontend --------------------------
echo [6/8] Restarting backend and frontend ^(postgres/redis left untouched^)...
docker compose %ENV_FILE% %COMPOSE_FILES% up -d --no-deps backend frontend
if errorlevel 1 (
    echo.
    echo FAILED: docker compose up failed. Check `docker compose ps` and
    echo container logs manually. Database/Redis were not affected.
    exit /b 1
)
echo.

REM --- 7. Show current status ------------------------------------------------
echo [7/8] Current container status:
docker compose %ENV_FILE% %COMPOSE_FILES% ps
echo.

REM --- 8. Health checks -------------------------------------------------------
echo [8/8] Running health checks...
set HEALTH_OK=1

curl -f -s -o nul http://localhost:8000/api/v1/health
if errorlevel 1 (
    echo   FAILED: backend health check ^(http://localhost:8000/api/v1/health^)
    set HEALTH_OK=0
) else (
    echo   OK - backend healthy.
)

curl -f -s -o nul http://localhost:3000/
if errorlevel 1 (
    echo   FAILED: frontend health check ^(http://localhost:3000/^)
    set HEALTH_OK=0
) else (
    echo   OK - frontend responding.
)

echo.
echo ============================================================
if "!HEALTH_OK!"=="1" (
    echo  DEPLOYMENT SUCCEEDED
    echo ============================================================
    exit /b 0
) else (
    echo  DEPLOYMENT COMPLETED BUT HEALTH CHECKS FAILED
    echo  Containers were restarted - check logs before trusting this
    echo  deploy. Postgres/Redis and their data were not affected.
    echo ============================================================
    exit /b 1
)
