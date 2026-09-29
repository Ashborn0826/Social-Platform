# smoke-test.ps1
# End-to-end smoke test for Project 2.
# Run from project root:  .\smoke-test.ps1
#
# Checks:
#  1. Infrastructure (Postgres + Memurai/Redis up?)
#  2. Backend (uvicorn running? pytest passes? key endpoints respond?)
#  3. Frontend (npm build succeeds? dev server boots?)
#  4. End-to-end API roundtrip (signup -> feed -> list users)

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'

$pass = 0
$fail = 0

function Check($name, $scriptBlock) {
    try {
        $result = & $scriptBlock
        if ($result -eq $false) {
            Write-Host "  [FAIL] $name" -ForegroundColor Red
            $script:fail++
        } else {
            Write-Host "  [ OK ] $name" -ForegroundColor Green
            $script:pass++
        }
    } catch {
        Write-Host "  [FAIL] $name -- $_" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host ''
Write-Host '== Infrastructure ==' -ForegroundColor Cyan

Check 'Postgres on :5432' {
    (Test-NetConnection -ComputerName localhost -Port 5432 -InformationLevel Quiet) -eq 'True'
}

Check 'Memurai/Redis on :6379' {
    (Test-NetConnection -ComputerName localhost -Port 6379 -InformationLevel Quiet) -eq 'True'
}

Write-Host ''
Write-Host '== Backend (shell 1: uvicorn) ==' -ForegroundColor Cyan

Check 'uvicorn on :8000 (backend /health)' {
    try {
        $r = Invoke-WebRequest http://localhost:8000/health -UseBasicParsing -TimeoutSec 3
        $r.StatusCode -eq 200 -and ($r.Content -like '*"ok"*')
    } catch { $false }
}

Check 'backend pytest passes' {
    Set-Location $backend
    $output = & .venv\Scripts\python.exe -m pytest -q --no-header 2>&1 | Out-String
    Set-Location $root
    $last = ($output -split "`n" | Select-Object -Last 1).Trim()
    Write-Host "         $last"
    $output -match '(\d+)\s+passed' -and (-not ($output -match 'failed'))
}

Write-Host ''
Write-Host '== Frontend (shell 3: vite) ==' -ForegroundColor Cyan

Check 'frontend tsc build succeeds' {
    Set-Location $frontend
    $output = & npm run build 2>&1 | Out-String
    Set-Location $root
    $output -notmatch 'error TS'
}

Check 'frontend dev server on :5173' {
    try {
        $r = Invoke-WebRequest http://localhost:5173 -UseBasicParsing -TimeoutSec 3
        $r.StatusCode -eq 200
    } catch { $false }
}

Write-Host ''
Write-Host '== End-to-end API roundtrip (backend must be running) ==' -ForegroundColor Cyan

# signup
$body = '{"email":"smoke@test.com","password":"CorrectHorse9","display_name":"Smoke"}'
try {
    $r = Invoke-WebRequest http://localhost:8000/api/auth/signup `
        -Method POST -ContentType 'application/json' -Body $body -UseBasicParsing -TimeoutSec 3
    $token = ($r.Content | ConvertFrom-Json).access_token
    if ($token -and $token.Length -gt 20) {
        Write-Host '  [ OK ] signup -> access_token issued' -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host "  [FAIL] signup -> $($r.Content)" -ForegroundColor Red
        $script:fail++
    }
} catch {
    Write-Host "  [FAIL] signup -- $_" -ForegroundColor Red
    $script:fail++
}

if ($token) {
    $headers = @{ Authorization = "Bearer $token" }

    # feed (authed)
    try {
        $r = Invoke-WebRequest http://localhost:8000/api/feed `
            -Headers $headers -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) {
            Write-Host '  [ OK ] GET /api/feed (authed) -> 200' -ForegroundColor Green
            $script:pass++
        } else {
            Write-Host "  [FAIL] feed -> $($r.StatusCode)" -ForegroundColor Red
            $script:fail++
        }
    } catch {
        Write-Host "  [FAIL] feed -- $_" -ForegroundColor Red
        $script:fail++
    }

    # users (authed)
    try {
        $r = Invoke-WebRequest http://localhost:8000/api/users `
            -Headers $headers -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) {
            Write-Host '  [ OK ] GET /api/users (authed) -> 200' -ForegroundColor Green
            $script:pass++
        } else {
            Write-Host "  [FAIL] users -> $($r.StatusCode)" -ForegroundColor Red
            $script:fail++
        }
    } catch {
        Write-Host "  [FAIL] users -- $_" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host ''
Write-Host '=' * 50
if ($fail -eq 0) {
    Write-Host "All checks passed ($pass/$pass)" -ForegroundColor Green
    exit 0
} else {
    Write-Host "Some checks failed: $fail failed, $pass passed" -ForegroundColor Yellow
    Write-Host ''
    Write-Host 'Things to check:' -ForegroundColor Yellow
    Write-Host '  - Are all 3 shells running? (uvicorn, worker, vite)'
    Write-Host '  - Is Postgres running? (Get-Service postgresql-x64-18)'
    Write-Host '  - Is Memurai running? (Get-Service Memurai)'
    Write-Host '  - Run "alembic upgrade head" in backend/ if schema is missing'
    exit 1
}
