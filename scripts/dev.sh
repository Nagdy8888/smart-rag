#!/usr/bin/env bash
# WSL2 equivalent of scripts/dev.ps1 — hosted-runtime Compose only.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -f .env.compose ]]; then
  echo "Missing .env.compose. Wire hosted Supabase with scripts/ops/wire_hosted_ingest_env.py before starting Compose." >&2
  exit 1
fi
required=(
  SUPABASE_URL
  API_SUPABASE_DB_URL
  WORKER_SUPABASE_DB_URL
  LANGGRAPH_CHECKPOINT_URL
  NEXT_PUBLIC_SUPABASE_URL
  NEXT_PUBLIC_SUPABASE_ANON_KEY
)
missing=()
for name in "${required[@]}"; do
  if ! grep -Eq "^[[:space:]]*${name}[[:space:]]*=[[:space:]]*[^[:space:]#].*" .env.compose; then
    missing+=("${name}")
  fi
done
if ((${#missing[@]})); then
  echo "Hosted Compose env is incomplete. Missing names: ${missing[*]}" >&2
  exit 1
fi
eval "$(uv run python -c "
from pathlib import Path
import shlex
for line in Path('.env.compose').read_text(encoding='utf-8').splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith('#') or '=' not in stripped:
        continue
    name, value = stripped.split('=', 1)
    name = name.strip()
    value = value.strip().strip(chr(34)).strip(chr(39))
    if name:
        print(f'export {name}={shlex.quote(value)}')
")"
docker compose --env-file .env.compose up --build -d
auth_host="$(docker compose --env-file .env.compose exec -T api python -c "import os; from urllib.parse import urlparse; print(urlparse(os.environ.get('SUPABASE_URL','')).hostname or '')")"
auth_host="$(echo "$auth_host" | tr -d '[:space:]')"
if [[ "$auth_host" == "127.0.0.1" || "$auth_host" == "localhost" || "$auth_host" == "host.docker.internal" ]]; then
  echo "API SUPABASE_URL host is the local fixture ($auth_host). Hosted browser sessions will 401." >&2
  exit 1
fi
echo "API Auth JWKS host: $auth_host"
echo "Canonical data: hosted Supabase (not local :54322)"
echo "Stop with: ./scripts/stop.sh"
