#Requires -Version 5.1
<#
.SYNOPSIS
  Start hosted-runtime laptop Compose sidecars and the host ingest worker.
.DESCRIPTION
  Requires a pre-wired ignored Compose env with hosted Auth and separate
  transaction/session DSNs. Builds the parser image, starts ParadeDB,
  both Valkeys, ClamAV, crawl-proxy, api, and frontend via base plus
  packet8 (loopback-only host ports). Launches the approved host ingest
  worker. Does not start the distroless Compose worker or local Supabase.
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

Write-Host "Building parser sandbox image (profile parser-build) ..."
docker compose --env-file $EnvFile --profile parser-build build parser-sandbox
if ($LASTEXITCODE -ne 0) {
  throw "parser-sandbox image build failed."
}

Write-Host "Starting hosted-runtime Docker Compose stack with packet8 loopback overlay ..."
docker compose --env-file $EnvFile -f docker-compose.yml -f docker-compose.packet8.yml up --build -d --wait paradedb valkey-limits valkey-cache clamav crawl-proxy api frontend
if ($LASTEXITCODE -ne 0) {
  throw "Compose up failed."
}

$authHost = docker compose --env-file $EnvFile exec -T api python -c "import os; from urllib.parse import urlparse; print(urlparse(os.environ.get('SUPABASE_URL','')).hostname or '')"
$authHost = "$authHost".Trim()
if ($authHost -in @("127.0.0.1", "localhost", "host.docker.internal")) {
  throw ("API SUPABASE_URL host is the local fixture ({0}). Hosted browser sessions will 401. Recreate with .env.compose loaded into the process." -f $authHost)
}
Write-Host "API Auth JWKS host: $authHost"

$logsDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
$logPath = Join-Path $logsDir "laptop-ingest-worker.log"
$errPath = Join-Path $logsDir "laptop-ingest-worker.err.log"
$metaPath = Join-Path $logsDir "laptop-ingest-worker.meta.json"
$launcher = "scripts/ops/run_laptop_ingest_worker.py"
Write-Host "Starting host ingest worker (logs gitignored) ..."
$proc = Start-Process -FilePath "uv" -WorkingDirectory $Root -ArgumentList @("run", "python", $launcher) -RedirectStandardOutput $logPath -RedirectStandardError $errPath -PassThru -WindowStyle Hidden
Start-Sleep -Milliseconds 400
$live = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
if (-not $live) {
  throw "Host ingest worker exited before metadata could be recorded. See logs/laptop-ingest-worker.log."
}
$commandLine = (Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $live.Id)).CommandLine
if (-not $commandLine) {
  $commandLine = "uv run python $launcher"
}
$meta = [ordered]@{
  pid = [int]$live.Id
  start_time = $live.StartTime.ToUniversalTime().ToString("o")
  command_line = [string]$commandLine
  launcher = $launcher
}
$meta | ConvertTo-Json | Set-Content -Path $metaPath -Encoding utf8
Write-Host ("Host ingest worker pid={0}" -f $live.Id)

Write-Host ""
Write-Host "Developer endpoints (when healthy):"
$apiPort = if ($env:API_HOST_PORT) { $env:API_HOST_PORT } else { "8000" }
$fePort = if ($env:FRONTEND_HOST_PORT) { $env:FRONTEND_HOST_PORT } else { "3000" }
Write-Host "  Frontend:  http://localhost:$fePort"
Write-Host "  API docs:  http://localhost:$apiPort/docs"
Write-Host "  API live:  http://localhost:$apiPort/health/live"
Write-Host "Packet8 loopback: 127.0.0.1:54329 127.0.0.1:13310 127.0.0.1:18080"
Write-Host "Host ingest worker: uv run python scripts/ops/run_laptop_ingest_worker.py"
Write-Host "Canonical data: hosted Supabase"
Write-Host "Stop with:  .\scripts\stop.ps1"
