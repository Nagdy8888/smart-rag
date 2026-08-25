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
docker compose --env-file .env.compose up --build -d
echo "Canonical data: hosted Supabase (not local :54322)"
echo "Stop with: ./scripts/stop.sh"
