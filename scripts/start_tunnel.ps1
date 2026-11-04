$ErrorActionPreference = "Stop"

$command = Get-Command cloudflared -ErrorAction SilentlyContinue
$cloudflared = if ($command) {
    $command.Source
} else {
    @(
        "C:\Program Files\cloudflared\cloudflared.exe",
        "C:\Program Files (x86)\cloudflared\cloudflared.exe",
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\cloudflared.exe")
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if (-not $cloudflared) {
    throw "cloudflared is not installed. Install it with: winget install --id Cloudflare.cloudflared"
}

Write-Host "Starting a Cloudflare Quick Tunnel for http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Copy the https://...trycloudflare.com URL into the Factly connection settings." -ForegroundColor DarkGray
& $cloudflared tunnel --url http://127.0.0.1:8000 --no-autoupdate
