#Requires -Version 5.1
<#
.SYNOPSIS
  Verify Phase 1 local foundation health without claiming later-phase readiness.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$EnvFile = if (Test-Path "$Root\.env.compose") { "$Root\.env.compose" } else { "$Root\.env.example" }

Write-Host "Using env file: $EnvFile"

function Assert-HttpOk([string]$Url, [string]$ExpectSubstring) {
  $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15
  if ($resp.StatusCode -ne 200) { throw "HTTP $($resp.StatusCode) for $Url" }
  if ($ExpectSubstring -and ($resp.Content -notmatch [regex]::Escape($ExpectSubstring))) {
    throw "Response for $Url missing '$ExpectSubstring': $($resp.Content)"
  }
  Write-Host "OK $Url"
}

# Published endpoints
Assert-HttpOk "http://127.0.0.1:8000/health/live" "live"
Assert-HttpOk "http://127.0.0.1:8000/health/ready" "unconfigured"
Assert-HttpOk "http://127.0.0.1:3000" "Smart RAG"

# Private ports must not be published
$ports = docker compose --env-file $EnvFile ps --format json | ConvertFrom-Json
$private = @("paradedb", "valkey-limits", "valkey-cache", "crawl-proxy")
foreach ($name in $private) {
  $svc = $ports | Where-Object { $_.Service -eq $name -or $_.Name -match $name }
  if (-not $svc) { Write-Host "WARN missing service in ps: $name"; continue }
  $publish = @($svc.Publishers)
  $hostPublished = @($publish | Where-Object { $_.PublishedPort -and ([int]$_.PublishedPort) -gt 0 })
  if ($hostPublished.Count -gt 0) {
    throw "Private service $name has published ports: $($hostPublished | ConvertTo-Json -Compress)"
  }
  Write-Host "OK private (no host publish): $name"
}

# ParadeDB pg_search via exec
$ext = docker compose --env-file $EnvFile exec -T paradedb psql -U paradedb -d paradedb -tAc "SELECT extname FROM pg_extension WHERE extname='pg_search'"
if (($ext.Trim()) -ne "pg_search") { throw "pg_search not installed: '$ext'" }
Write-Host "OK ParadeDB pg_search"

# Crawl proxy deny from private network
$deny = docker compose --env-file $EnvFile exec -T api python -c "import urllib.request; import urllib.error
try:
  urllib.request.urlopen(urllib.request.Request('http://crawl-proxy:8080/fetch', data=b'{}', method='POST'), timeout=5)
  raise SystemExit('expected deny')
except urllib.error.HTTPError as e:
  print(e.code)
"
if ($deny.Trim() -ne "403") { throw "crawl proxy did not deny: $deny" }
Write-Host "OK crawl-proxy deny-by-default"

# Non-root api user
$user = docker compose --env-file $EnvFile exec -T api python -c "import os; print(os.getuid())"
if ($user.Trim() -ne "10001") { throw "api not running as uid 10001: $user" }
Write-Host "OK api non-root uid 10001"

Write-Host "Local foundation verification passed (readiness remains unconfigured for business deps)."
