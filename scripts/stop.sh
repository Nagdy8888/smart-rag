#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
docker compose --env-file .env stop
if command -v supabase >/dev/null 2>&1; then
  supabase stop
fi
echo "Stopped; volumes preserved."
