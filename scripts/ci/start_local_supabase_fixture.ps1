#Requires -Version 5.1
<#
.SYNOPSIS
  Start the isolated local Supabase destructive-test fixture.
.DESCRIPTION
  Starts workspace-pinned CLI Supabase and ensures LOGIN wrapper
  app_runtime. This is not the product runtime. Chat and application
  writes must target hosted Supabase.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$SupabaseCli = "$Root\node_modules\.bin\supabase.cmd"
if (-not (Test-Path $SupabaseCli)) {
  throw "Pinned Supabase CLI is unavailable. Run pnpm install --frozen-lockfile first."
}

Write-Host "Starting local Supabase test fixture with the workspace-pinned CLI..."
& pnpm exec supabase start | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Supabase CLI failed to start the local test fixture."
}

Write-Host "Ensuring LOGIN wrapper app_runtime on the local fixture..."
uv run python "$Root\scripts\ops\ensure_app_runtime_role.py"
if ($LASTEXITCODE -ne 0) {
  throw "app_runtime LOGIN wrapper is missing on the local fixture."
}

Write-Host "Local Supabase fixture is ready for destructive reset/RLS/CI tests only."
