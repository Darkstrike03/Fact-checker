$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found. Run: python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt"
}

Write-Host "Serving Factly at http://127.0.0.1:5500" -ForegroundColor Cyan
& $python -m http.server 5500 --directory docs --bind 127.0.0.1
