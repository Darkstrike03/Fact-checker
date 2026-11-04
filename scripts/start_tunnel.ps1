$ErrorActionPreference = "Stop"

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    throw "cloudflared is not installed. Install it with: winget install --id Cloudflare.cloudflared"
}

Write-Host "Starting a Cloudflare Quick Tunnel for http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Copy the https://...trycloudflare.com URL into the Factly connection settings." -ForegroundColor DarkGray
& $cloudflared.Source tunnel --url http://127.0.0.1:8000
