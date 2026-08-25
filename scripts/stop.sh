#!/usr/bin/env bash
# WSL2 equivalent of scripts/stop.ps1 — Compose only; local fixture untouched.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f .env.compose ]]; then
  ENV_FILE=.env.compose
elif [[ -f .env ]]; then
  ENV_FILE=.env
else
  echo "No Compose environment file found. Run ./scripts/dev.sh first." >&2
  exit 1
fi
docker compose --env-file "$ENV_FILE" stop
echo "Compose services stopped. Volumes preserved. Local Supabase fixture was not touched."
