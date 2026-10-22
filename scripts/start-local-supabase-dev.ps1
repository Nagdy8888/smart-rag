# Resume the already-provisioned temporary local development stack.
# This does not initialize/reset data or contact the hosted Supabase project.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    if (-not (Test-Path -LiteralPath '.env.local-supabase')) {
        throw 'Local Supabase has not been provisioned: .env.local-supabase is missing.'
    }
    $localContainers = @(
        'supabase_db_smart-rag-local-dev',
        'supabase_auth_smart-rag-local-dev',
        'supabase_rest_smart-rag-local-dev',
        'supabase_storage_smart-rag-local-dev',
        'supabase_kong_smart-rag-local-dev'
    )
    foreach ($container in $localContainers) {
        & docker start $container
        if ($LASTEXITCODE -ne 0) { throw "Could not start $container" }
    }
    & docker compose --env-file .env.local-supabase `
        -f docker-compose.yml -f docker-compose.packet8.yml `
        -f docker-compose.local-supabase.yml up -d --no-build `
        paradedb valkey-limits valkey-cache crawl-proxy api
    if ($LASTEXITCODE -ne 0) { throw 'Local application startup failed.' }
    Write-Host 'Local API: http://127.0.0.1:8000/health/ready'
    Write-Host 'Start the frontend: pnpm --filter smart-rag-frontend dev --hostname 127.0.0.1 --port 3000'
} finally {
    Pop-Location
}
