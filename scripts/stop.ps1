#Requires -Version 5.1
<#
.SYNOPSIS
  Stop the matching host ingest worker and laptop Compose services.
.DESCRIPTION
  Stops the recorded host-worker PID only when command line and start
  time match this repository launcher. Missing, stale, or mismatched
  PIDs are reported and left untouched. Then stops Compose sidecars
  without starting, stopping, or resetting local Supabase.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$EnvFile = if (Test-Path "$Root\.env.compose") {
  "$Root\.env.compose"
} elseif (Test-Path "$Root\.env") {
  "$Root\.env"
} else {
  throw "No Compose environment file found. Run .\scripts\dev.ps1 first."
}

$metaPath = Join-Path $Root "logs\laptop-ingest-worker.meta.json"
$launcher = "scripts/ops/run_laptop_ingest_worker.py"
if (-not (Test-Path $metaPath)) {
  Write-Host "Host ingest worker metadata missing. No PID was killed."
} else {
  $meta = Get-Content $metaPath -Raw | ConvertFrom-Json
  $workerPid = [int]$meta.pid
  $recordedStart = [string]$meta.start_time
  $recordedCmd = [string]$meta.command_line
  $live = Get-Process -Id $workerPid -ErrorAction SilentlyContinue
  if (-not $live) {
    Write-Host ("Host ingest worker pid={0} is stale and was left untouched." -f $workerPid)
  } else {
    $liveStart = $live.StartTime.ToUniversalTime().ToString("o")
    $liveCmd = (Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $workerPid)).CommandLine
    if (-not $liveCmd) { $liveCmd = "" }
    $matchesLauncher = ($recordedCmd -like "*$launcher*") -and ($liveCmd -like "*$launcher*")
    if ($liveStart -ne $recordedStart -or -not $matchesLauncher) {
      Write-Host ("Host ingest worker pid={0} does not match this launcher and was left untouched." -f $workerPid)
    } else {
      Stop-Process -Id $workerPid
      Write-Host ("Stopped host ingest worker pid={0}." -f $workerPid)
    }
  }
}

docker compose --env-file $EnvFile -f docker-compose.yml -f docker-compose.packet8.yml stop
Write-Host "Compose services stopped. Volumes preserved. Local Supabase fixture was not touched."
