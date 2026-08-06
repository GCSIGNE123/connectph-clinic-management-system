<#
.SYNOPSIS
    Bootstraps a local development environment for the CONNECT.PH Clinic Platform (Windows/PowerShell).

.DESCRIPTION
    Copies environment file templates, installs frontend and backend dependencies,
    runs database migrations, and seeds foundational data (roles/permissions).

    This script is intentionally explicit and step-by-step rather than fully
    silent/automatic — read the output at each step. It assumes Docker Desktop
    is running if you want to use the local Postgres/Redis containers; you can
    also point at a Supabase project instead (see docs/DEPLOYMENT.md).

.EXAMPLE
    ./scripts/setup-dev.ps1
#>

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "==> CONNECT.PH Clinic Platform — local dev setup" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Environment files
# ---------------------------------------------------------------------------
Write-Host "`n[1/5] Copying environment file templates..." -ForegroundColor Yellow

$envPairs = @(
    @{ Example = "frontend/.env.example"; Target = "frontend/.env.local" },
    @{ Example = "backend/.env.example";  Target = "backend/.env" }
)

foreach ($pair in $envPairs) {
    $examplePath = Join-Path $RepoRoot $pair.Example
    $targetPath  = Join-Path $RepoRoot $pair.Target

    if (-not (Test-Path $examplePath)) {
        Write-Host "  ! Skipping: $($pair.Example) not found yet." -ForegroundColor DarkYellow
        continue
    }

    if (Test-Path $targetPath) {
        Write-Host "  - $($pair.Target) already exists, leaving it untouched." -ForegroundColor DarkGray
    } else {
        Copy-Item $examplePath $targetPath
        Write-Host "  + Created $($pair.Target) from $($pair.Example)" -ForegroundColor Green
        Write-Host "    -> Edit it now and fill in real values (DB, JWT secret, Supabase keys, etc.)." -ForegroundColor DarkGray
    }
}

# ---------------------------------------------------------------------------
# 2. Start infra (Postgres + Redis) via Docker Compose
# ---------------------------------------------------------------------------
Write-Host "`n[2/5] Starting Postgres + Redis via Docker Compose..." -ForegroundColor Yellow
$composeFile = Join-Path $RepoRoot "docker/docker-compose.yml"

try {
    docker compose -f $composeFile up -d postgres redis
    Write-Host "  + Postgres and Redis containers are starting." -ForegroundColor Green
} catch {
    Write-Host "  ! Could not start Docker containers automatically. Is Docker Desktop running?" -ForegroundColor Red
    Write-Host "    You can run this manually later:  docker compose -f docker/docker-compose.yml up -d postgres redis" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# 3. Backend: virtualenv + dependencies
# ---------------------------------------------------------------------------
Write-Host "`n[3/5] Setting up backend (Python) environment..." -ForegroundColor Yellow
Push-Location (Join-Path $RepoRoot "backend")
try {
    if (-not (Test-Path ".venv")) {
        Write-Host "  Creating virtualenv..." -ForegroundColor DarkGray
        python -m venv .venv
    }

    Write-Host "  Installing backend dependencies..." -ForegroundColor DarkGray
    & ".venv\Scripts\pip.exe" install --upgrade pip
    if (Test-Path "pyproject.toml") {
        & ".venv\Scripts\pip.exe" install -e ".[dev]"
    } elseif (Test-Path "requirements.txt") {
        & ".venv\Scripts\pip.exe" install -r requirements.txt
    } else {
        Write-Host "  ! No pyproject.toml or requirements.txt found yet — skipping install." -ForegroundColor DarkYellow
    }
    Write-Host "  + Backend dependencies installed." -ForegroundColor Green
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 4. Frontend: npm install
# ---------------------------------------------------------------------------
Write-Host "`n[4/5] Installing frontend (npm) dependencies..." -ForegroundColor Yellow
Push-Location (Join-Path $RepoRoot "frontend")
try {
    if (Test-Path "package.json") {
        npm install
        Write-Host "  + Frontend dependencies installed." -ForegroundColor Green
    } else {
        Write-Host "  ! frontend/package.json not found — skipping npm install." -ForegroundColor DarkYellow
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 5. Database migrations + seed data
# ---------------------------------------------------------------------------
Write-Host "`n[5/5] Running database migrations and seed data..." -ForegroundColor Yellow
Push-Location (Join-Path $RepoRoot "backend")
try {
    Write-Host "  Waiting a few seconds for Postgres container to be ready..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 5

    & ".venv\Scripts\alembic.exe" upgrade head
    Write-Host "  + Migrations applied." -ForegroundColor Green

    if (Test-Path "app/db/seed.py") {
        & ".venv\Scripts\python.exe" -m app.db.seed
        Write-Host "  + Seed data (roles, permissions) applied." -ForegroundColor Green
    } else {
        Write-Host "  ! app/db/seed.py not found yet — skipping seed step. Seed roles/permissions manually." -ForegroundColor DarkYellow
    }
} catch {
    Write-Host "  ! Migration/seed step failed. Check backend/.env DATABASE_URL and that Postgres is reachable." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor DarkGray
} finally {
    Pop-Location
}

Write-Host "`n==> Setup complete." -ForegroundColor Cyan
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  Backend:  cd backend; .venv\Scripts\activate; uvicorn app.main:app --reload --port 8000"
Write-Host "  Frontend: cd frontend; npm run dev"
Write-Host "  Docs:     http://localhost:8000/docs   |   App: http://localhost:3000"
