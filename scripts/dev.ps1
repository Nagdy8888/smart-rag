#Requires -Version 5.1
<#
.SYNOPSIS
  Start hosted-runtime laptop Compose sidecars. Does not start local Supabase.
.DESCRIPTION
  Requires a pre-wired ignored Compose env with hosted Auth and separate
  transaction/session DSNs. Starts ParadeDB, Valkey, crawl-proxy, api, worker,
  and frontend against the cloud Supabase project.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path "$Root\.env.compose")) {
  throw "Missing .env.compose. Wire hosted Supabase with scripts/ops/wire_hosted_ingest_env.py before starting Compose."
}
$EnvFile = "$Root\.env.compose"

$required = @(
  "SUPABASE_URL",
  "API_SUPABASE_DB_URL",
  "WORKER_SUPABASE_DB_URL",
  "LANGGRAPH_CHECKPOINT_URL",
  "NEXT_PUBLIC_SUPABASE_URL",
  "NEXT_PUBLIC_SUPABASE_ANON_KEY"
)
$present = @{}
Get-Content $EnvFile | ForEach-Object {
  if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$') {
    $name = $Matches[1]
    $value = $Matches[2].Trim().Trim('"').Trim("'")
    if ($value -ne "") {
      $present[$name] = $true
    }
  }
}
$missing = $required | Where-Object { -not $present.ContainsKey($_) }
if ($missing.Count -gt 0) {
  throw ("Hosted Compose env is incomplete. Missing names: {0}" -f ($missing -join ", "))
}

# Process env wins Compose interpolation. Export .env.compose into this
# process so a stale project `.env` cannot override SUPABASE_URL.
Get-Content $EnvFile | ForEach-Object {
  $line = $_.Trim()
  if (-not $line -or $line.StartsWith("#")) {
    return
  }
  $parts = $line.Split("=", 2)
  if ($parts.Count -ne 2) {
    return
  }
  $name = $parts[0].Trim()
  $value = $parts[1].Trim().Trim('"').Trim("'")
  if ($name) {
    Set-Item -Path ("Env:{0}" -f $name) -Value $value
  }
}

Write-Host "Starting hosted-runtime Docker Compose stack with .env.compose ..."
docker compose --env-file $EnvFile up --build -d

$authHost = docker compose --env-file $EnvFile exec -T api python -c "import os; from urllib.parse import urlparse; print(urlparse(os.environ.get('SUPABASE_URL','')).hostname or '')"
$authHost = "$authHost".Trim()
if ($authHost -in @("127.0.0.1", "localhost", "host.docker.internal")) {
  throw ("API SUPABASE_URL host is the local fixture ({0}). Hosted browser sessions will 401. Recreate with .env.compose loaded into the process." -f $authHost)
}
Write-Host "API Auth JWKS host: $authHost"

Write-Host ""
Write-Host "Developer endpoints (when healthy):"
$apiPort = if ($env:API_HOST_PORT) { $env:API_HOST_PORT } else { "8000" }
$fePort = if ($env:FRONTEND_HOST_PORT) { $env:FRONTEND_HOST_PORT } else { "3000" }
Write-Host "  Frontend:  http://localhost:$fePort"
Write-Host "  API docs:  http://localhost:$apiPort/docs"
Write-Host "  API live:  http://localhost:$apiPort/health/live"
Write-Host "Private (no host ports): paradedb, valkey-limits, valkey-cache, crawl-proxy"
Write-Host "Canonical data: hosted Supabase"
Write-Host "Stop with:  .\scripts\stop.ps1"
