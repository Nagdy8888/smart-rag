#Requires -Version 5.1
<#
.SYNOPSIS
  Destructive local reset — removes Compose volumes after explicit confirmation.
#>
param(
  [switch]$ConfirmReset
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $ConfirmReset) {
  Write-Error "Refusing destructive reset. Re-run with -ConfirmReset after backing up any needed local data."
  exit 2
}

docker compose --env-file .env down -v --remove-orphans
Write-Host "Compose stack removed including volumes."

$supabase = Get-Command supabase -ErrorAction SilentlyContinue
if ($supabase) {
  & supabase db reset --yes
  Write-Host "Supabase local DB reset requested."
}
