@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  CONNECT.PH Clinic Platform - Production Deployment (Phase 3)
REM
REM  Run this on the clinic Server PC, from the repo root, after
REM  new commits have landed on origin/main. It:
REM    1. Refuses to run if the checkout has uncommitted local changes.
REM    2. Pulls the latest code with `git pull --ff-only` (never merges).
REM    3. Builds only the backend/frontend images (docker/docker-compose.prod.yml).
REM    4. Restarts only backend/frontend - postgres and redis are left
REM       running untouched, their data volumes are never touched.
REM    5. Shows `docker compose ps`.
REM    6. Runs basic HTTP health checks and reports success/failure.
REM
REM  Deliberately does NOT:
REM    - run `git reset --hard`, or any destructive git command
REM    - run `docker compose down` or `down -v` (never deletes volumes)
REM    - touch postgres or redis at all
REM    - run Alembic migrations (see docker-compose.prod.yml's backend
REM      command override - migrations are a separate, manual step)
REM ============================================================

cd /d "%~dp0"

set COMPOSE_FILES=-f docker\docker-compose.yml -f docker\docker-compose.prod.yml

echo ============================================================
echo  CONNECT.PH Clinic Platform - Production Deployment
echo ============================================================
echo.

REM --- 1. Refuse to deploy over uncommitted local changes ----------------
echo [1/6] Checking for uncommitted local changes...
set DIRTY=
for /f "delims=" %%L in ('git status --porcelain 2^>^&1') do set DIRTY=1
if defined DIRTY (
    echo.
    echo FAILED: this checkout has uncommitted local changes.
    echo Resolve or discard them before deploying - showing status below:
    echo.
    git status --short
    echo.
    echo Nothing was pulled, built, or restarted.
    exit /b 1
)
echo   OK - working tree clean.
echo.

REM --- 2. Pull latest code (fast-forward only) ----------------------------
echo [2/6] Pulling latest code (git pull --ff-only)...
git pull --ff-only
if errorlevel 1 (
    echo.
    echo FAILED: git pull --ff-only did not succeed - local and origin/main
    echo have diverged, or the remote is unreachable. Resolve manually
    echo ^(this script will never merge or force-overwrite^).
    echo Nothing was built or restarted.
    exit /b 1
)
echo.

REM --- 3. Build application images only -----------------------------------
echo [3/6] Building backend and frontend images...
docker compose %COMPOSE_FILES% build backend frontend
if errorlevel 1 (
    echo.
    echo FAILED: docker compose build failed. Previous containers are
    echo still running, untouched - nothing has been restarted.
    exit /b 1
)
echo.

REM --- 4. Restart/recreate only backend + frontend ------------------------
echo [4/6] Restarting backend and frontend ^(postgres/redis left untouched^)...
docker compose %COMPOSE_FILES% up -d --no-deps backend frontend
if errorlevel 1 (
    echo.
    echo FAILED: docker compose up failed. Check `docker compose ps` and
    echo container logs manually. Database/Redis were not affected.
    exit /b 1
)
echo.

REM --- 5. Show current status ----------------------------------------------
echo [5/6] Current container status:
docker compose %COMPOSE_FILES% ps
echo.

REM --- 6. Health checks -----------------------------------------------------
echo [6/6] Running health checks...
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
