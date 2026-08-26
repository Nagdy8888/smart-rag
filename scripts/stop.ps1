#Requires -Version 5.1
<#
.SYNOPSIS
  Stop laptop Compose services while preserving volumes.
.DESCRIPTION
  Stops hosted-runtime Compose sidecars. Does not start, stop, or reset
  local Supabase; that stack is a separately labelled test fixture.
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

docker compose --env-file $EnvFile stop
Write-Host "Compose services stopped. Volumes preserved. Local Supabase fixture was not touched."
