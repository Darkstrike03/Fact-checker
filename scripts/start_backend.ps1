$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found. Run: python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt"
}

if (-not (Test-Path -LiteralPath (Join-Path $root ".env"))) {
    Write-Host "Warning: .env is missing. Copy .env.example to .env and set ACCESS_CODE." -ForegroundColor Yellow
}

Write-Host "Starting Factly API on http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Make sure LM Studio is running on port 1234." -ForegroundColor DarkGray
& $python -m uvicorn api:app --host 127.0.0.1 --port 8000
