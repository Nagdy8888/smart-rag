#Requires -Version 5.1
<#
.SYNOPSIS
  Verify Phase 1 local foundation health without claiming later-phase readiness.
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

Write-Host "Using env file: $EnvFile"

function Assert-HttpOk([string]$Url, [string]$ExpectSubstring) {
  $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15
  if ($resp.StatusCode -ne 200) { throw "HTTP $($resp.StatusCode) for $Url" }
  if ($ExpectSubstring -and ($resp.Content -notmatch [regex]::Escape($ExpectSubstring))) {
    throw "Response for $Url missing '$ExpectSubstring': $($resp.Content)"
  }
  Write-Host "OK $Url"
}

function Assert-ValkeyPolicy(
  [string]$Service,
  [string]$AuthenticatedCommand,
  [string]$ExpectedPolicy
) {
  $ping = docker compose --env-file $EnvFile exec -T $Service sh -c "$AuthenticatedCommand ping"
  if ($LASTEXITCODE -ne 0 -or (($ping -join "`n").Trim()) -ne "PONG") {
    throw "$Service authenticated ping failed."
  }

  $policy = docker compose --env-file $EnvFile exec -T $Service sh -c "$AuthenticatedCommand config get maxmemory-policy"
  $policyLines = @(($policy -join "`n").Trim() -split "\r?\n")
  if ($LASTEXITCODE -ne 0 -or $policyLines[-1].Trim() -ne $ExpectedPolicy) {
    throw "$Service policy mismatch: expected $ExpectedPolicy, received '$($policyLines[-1])'."
  }

  $unauthenticated = docker compose --env-file $EnvFile exec -T $Service valkey-cli --raw ping 2>&1
  if (($unauthenticated -join "`n") -notmatch "NOAUTH") {
    throw "$Service accepted an unauthenticated ping."
  }

  Write-Host "OK $Service authenticated with $ExpectedPolicy policy"
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
  if (-not $svc) { throw "Required private service missing from Compose: $name" }
  $publish = @($svc.Publishers)
  $hostPublished = @($publish | Where-Object { $_.PublishedPort -and ([int]$_.PublishedPort) -gt 0 })
  if ($hostPublished.Count -gt 0) {
    throw "Private service $name has published ports: $($hostPublished | ConvertTo-Json -Compress)"
  }
  Write-Host "OK private (no host publish): $name"
}

# Authenticated Valkey behavior and independent eviction policies
Assert-ValkeyPolicy "valkey-limits" 'valkey-cli -a "$VALKEY_LIMITS_PASSWORD" --no-auth-warning --raw' "noeviction"
Assert-ValkeyPolicy "valkey-cache" 'valkey-cli -a "$VALKEY_CACHE_PASSWORD" --no-auth-warning --raw' "allkeys-lru"

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

# Non-root application users
foreach ($service in @("api", "worker", "frontend")) {
  $user = docker compose --env-file $EnvFile exec -T $service id -u
  if ($user.Trim() -ne "10001") { throw "$service not running as uid 10001: $user" }
  Write-Host "OK $service non-root uid 10001"
}

# Runtime profile: default is MOCK_MODEL_MODE=true. Live OpenAI is local opt-in
# only; real company content stays prohibited until org matrices are verified.
$mockMode = docker compose --env-file $EnvFile exec -T api sh -c 'printf %s "$MOCK_MODEL_MODE"'
$openaiKeyLen = docker compose --env-file $EnvFile exec -T api sh -c 'printf %s "${#OPENAI_API_KEY}"'
if ($mockMode.Trim() -eq "true") {
  Write-Host "OK API mock-model profile"
} elseif ($mockMode.Trim() -eq "false" -and [int]$openaiKeyLen.Trim() -gt 0) {
  Write-Host "OK API live-model profile (synthetic corpus only; OpenAI key present)"
} else {
  throw "API MOCK_MODEL_MODE must be true, or false with OPENAI_API_KEY set in the container."
}

Write-Host "Local foundation verification passed; business readiness remains intentionally unconfigured."
