#Requires -Version 5.1
<#
.SYNOPSIS
  Destructive local reset; removes Compose volumes after explicit confirmation.
#>
param(
  [switch]$ConfirmReset
)

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

if (-not $ConfirmReset) {
  [Console]::Error.WriteLine(
    "Refusing destructive reset. Re-run with -ConfirmReset after backing up any needed local data."
  )
  exit 2
}

docker compose --env-file $EnvFile down -v --remove-orphans
Write-Host "Compose stack removed including volumes."

& pnpm exec supabase db reset --yes
Write-Host "Supabase local DB reset requested."
