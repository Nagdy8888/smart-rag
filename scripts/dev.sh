#!/usr/bin/env bash
# WSL2 equivalent of scripts/dev.ps1 — same Compose/.env contract.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi
if command -v supabase >/dev/null 2>&1; then
  supabase start
else
  echo "Supabase CLI not found — skipping local Supabase."
fi
docker compose --env-file .env up --build -d
echo "Stop with: ./scripts/stop.sh"
