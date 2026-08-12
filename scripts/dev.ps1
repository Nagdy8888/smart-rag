#Requires -Version 5.1
<#
.SYNOPSIS
  Start local Smart RAG foundation services (Supabase CLI if present + Compose).
.DESCRIPTION
  Starts digest-pinned ParadeDB, split Valkey, crawl-proxy, api, worker, and frontend
  in mock-model mode. Does not require AWS or a live OpenAI key.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path "$Root\.env")) {
  Copy-Item "$Root\.env.example" "$Root\.env"
  Write-Host "Created .env from .env.example — update passwords before shared use."
}

$supabase = Get-Command supabase -ErrorAction SilentlyContinue
if ($supabase) {
  Write-Host "Starting local Supabase (stock Phase 1 config)..."
  & supabase start
} else {
  Write-Host "Supabase CLI not found — skipping local Supabase. Install and re-run for Auth/Studio/Inbucket."
  Write-Host "Pin guidance: use the current Supabase CLI release documented at https://supabase.com/docs/guides/local-development"
}

Write-Host "Starting Docker Compose foundation stack..."
docker compose --env-file .env up --build -d

Write-Host ""
Write-Host "Developer endpoints (when healthy):"
$apiPort = if ($env:API_HOST_PORT) { $env:API_HOST_PORT } else { "8000" }
$fePort = if ($env:FRONTEND_HOST_PORT) { $env:FRONTEND_HOST_PORT } else { "3000" }
Write-Host "  Frontend:  http://localhost:$fePort"
Write-Host "  API docs:  http://localhost:$apiPort/docs"
Write-Host "  API live:  http://localhost:$apiPort/health/live"
Write-Host "Private (no host ports): paradedb, valkey-limits, valkey-cache, crawl-proxy"
Write-Host "Stop with:  .\scripts\stop.ps1"
Write-Host "Reset data: .\scripts\reset.ps1 -ConfirmReset"
