---
title: Local setup
owner: engineering-lead
status: draft
last-reviewed: 2026-08-19
audience: engineering
---

# Local setup

1. Install Docker Desktop (WSL2), uv, Node 20+, and pnpm 9.15+.
2. Run `uv sync --all-packages --group dev --python 3.11 --frozen`.
3. Run `pnpm install --frozen-lockfile`; this installs the workspace-pinned Supabase CLI.
4. Run `Copy-Item .env.example .env.compose` and set local passwords using `KEY=VALUE` syntax. Lifecycle scripts prefer `.env.compose`, then `.env`. Set `APP_RUNTIME_DB_PASSWORD` (or keep the example placeholder). See [LOCAL_RUNTIME_ROLES.md](../deployment/LOCAL_RUNTIME_ROLES.md).
5. Run `.\scripts\dev.ps1`. After Supabase starts, that script creates LOGIN wrapper `app_runtime` before Compose `up`. Then run `.\scripts\verify-local.ps1`.
6. For the Phase 9 local release candidate, freeze, build, and seed with
   `uv run python scripts/phase09_candidate.py all`. Candidate identity is
   `docker-compose.yml` only; do not use `docker-compose.packet8.yml` for
   that proof. See [LOCAL_RELEASE_CANDIDATE.md](../deployment/LOCAL_RELEASE_CANDIDATE.md).
7. To inspect the query graph in LangGraph Studio (unbound, no FastAPI
   admit), run `.\scripts\langgraph-studio.ps1` and open the printed Studio
   URL. Select `query_studio`. See [LANGGRAPH_STUDIO.md](./LANGGRAPH_STUDIO.md).

`dev.ps1` fails closed when the pinned Supabase CLI is unavailable. `stop.ps1` preserves Compose and Supabase data; `reset.ps1 -ConfirmReset` is the explicit destructive route.

See [CONFIGURATION.md](./CONFIGURATION.md), [TOOL_VERSIONS.md](./TOOL_VERSIONS.md),
[LANGGRAPH_STUDIO.md](./LANGGRAPH_STUDIO.md), [docs index](../README.md).
