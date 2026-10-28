# Windows PowerShell verification script
# Runs backend pytest, frontend typecheck, frontend tests, and production build.
# Requires PostgreSQL running with brandpr_test database available.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
Set-Location $rootDir

if (-not $env:TEST_DATABASE_URL) {
    $env:TEST_DATABASE_URL = "postgresql+psycopg://brandpr:brandpr_dev_password@localhost:5433/brandpr_test"
}

Write-Host "==> Checking Python environment..." -ForegroundColor Cyan
$pythonExe = Join-Path $rootDir "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

Write-Host "==> [1/4] Running backend pytest suite..." -ForegroundColor Cyan
Push-Location (Join-Path $rootDir "backend")
try {
    & $pythonExe -m pytest
    if ($LASTEXITCODE -ne 0) { throw "Backend pytest failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host "==> [2/4] Running frontend typecheck..." -ForegroundColor Cyan
Push-Location (Join-Path $rootDir "frontend")
try {
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { throw "Frontend typecheck failed with exit code $LASTEXITCODE" }

    Write-Host "==> [3/4] Running frontend tests..." -ForegroundColor Cyan
    npm test
    if ($LASTEXITCODE -ne 0) { throw "Frontend test suite failed with exit code $LASTEXITCODE" }

    Write-Host "==> [4/4] Running frontend production build..." -ForegroundColor Cyan
    $env:BACKEND_URL = "http://localhost:8000"
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

Write-Host "`nAll automated verification checks passed successfully!" -ForegroundColor Green
Write-Host "To execute live E2E browser and API test journeys, run:" -ForegroundColor Yellow
Write-Host "  node scripts/e2e_live.mjs"
Write-Host "  node scripts/e2e_review.mjs"
Write-Host "  node scripts/e2e_fact_impacts.mjs"
Write-Host "  node scripts/e2e_workflow.mjs"
Write-Host "  node scripts/e2e_guidelines.mjs"
Write-Host "  node scripts/e2e_campaigns.mjs"
Write-Host "  node scripts/e2e_security.mjs"

