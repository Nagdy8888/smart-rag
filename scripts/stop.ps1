#Requires -Version 5.1
<#
.SYNOPSIS
  Stop local Compose services while preserving volumes.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

docker compose --env-file .env stop
Write-Host "Compose services stopped. Volumes preserved."

$supabase = Get-Command supabase -ErrorAction SilentlyContinue
if ($supabase) {
  & supabase stop
  Write-Host "Local Supabase stopped (data retained unless you reset)."
}
