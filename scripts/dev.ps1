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

$EnvFile = if (Test-Path "$Root\.env.compose") {
  "$Root\.env.compose"
} elseif (Test-Path "$Root\.env") {
  "$Root\.env"
} else {
  Copy-Item "$Root\.env.example" "$Root\.env.compose"
  Write-Host "Created .env.compose from .env.example; update passwords before shared use."
  "$Root\.env.compose"
}

$SupabaseCli = "$Root\node_modules\.bin\supabase.cmd"
if (-not (Test-Path $SupabaseCli)) {
  throw "Pinned Supabase CLI is unavailable. Run pnpm install --frozen-lockfile first."
}

Write-Host "Starting local Supabase with the workspace-pinned CLI..."
& pnpm exec supabase start | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Supabase CLI failed to start the local stack."
}

Write-Host "Ensuring LOGIN wrapper app_runtime (app_api is NOLOGIN)..."
uv run python "$Root\scripts\ops\ensure_app_runtime_role.py"
if ($LASTEXITCODE -ne 0) {
  throw "app_runtime LOGIN wrapper is missing. Compose API/worker cannot use the postgres superuser."
}

Write-Host "Starting Docker Compose foundation stack with $EnvFile ..."
docker compose --env-file $EnvFile up --build -d

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
