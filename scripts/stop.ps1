#Requires -Version 5.1
<#
.SYNOPSIS
  Stop local Compose services while preserving volumes.
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

$SupabaseCli = "$Root\node_modules\.bin\supabase.cmd"
if (-not (Test-Path $SupabaseCli)) {
  throw "Pinned Supabase CLI is unavailable. Run pnpm install --frozen-lockfile first."
}

docker compose --env-file $EnvFile stop
Write-Host "Compose services stopped. Volumes preserved."

& pnpm exec supabase stop
Write-Host "Local Supabase stopped (data retained unless you reset)."
