# Smart RAG — Hybrid / Graph RAG platform

Greenfield monorepo for an authorized company RAG system: Hybrid retrieval (Supabase + private ParadeDB BM25), LightRAG graph leads resolved to canonical evidence, LangGraph orchestration, and a Next.js testing UI.

## Prerequisites

- Windows 10/11 with Docker Desktop (WSL2 backend recommended): 16 GB RAM / 4 cores / 40 GB free minimum
- [uv](https://docs.astral.sh/uv/) 0.11+, Node.js 20+, pnpm 9.15+
- Hosted Supabase project `smart-rag` for runtime Auth/Postgres/Storage
- The workspace-pinned [Supabase CLI](https://supabase.com/docs/guides/local-development), installed by pnpm (destructive-test fixture only)
- OpenAI key only for real-model evaluation; mock-model mode needs none

## Quick start

```powershell
uv sync --all-packages --group dev --python 3.11 --frozen
pnpm install --frozen-lockfile
# Wire hosted Auth + transaction/session DSNs into ignored .env.compose
uv run python scripts/ops/wire_hosted_ingest_env.py
.\scripts\dev.ps1
.\scripts\verify-local.ps1
```

Developer endpoints (when healthy):

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- API live: http://localhost:8000/health/live

Stop Compose (preserve volumes): `.\scripts\stop.ps1`  
Local destructive-test fixture: `.\scripts\ci\start_local_supabase_fixture.ps1`  
Destructive fixture reset: `.\scripts\reset.ps1 -ConfirmReset`

## Common commands

```powershell
uv sync --all-packages --group dev --python 3.11
uv run python scripts/check.py --tier fast
pnpm --filter smart-rag-frontend build
docker compose --env-file .env.example config --quiet
```

## Documentation

Full index (owner / status / last-reviewed): [docs/README.md](docs/README.md)

## Workspace layout

- `apps/backend` — FastAPI transport (`smart_rag_api`)
- `apps/worker` — durable job process (`smart_rag_worker`)
- `apps/agents` — LangGraph query/ingestion graphs (`smart_rag_agents`)
- `packages/core` — shared domain/settings/gateways (`smart_rag_core`)
- `apps/frontend` — Next.js App Router (`smart-rag-frontend`)

## Status

Phase 1 foundation was accepted on 2026-08-12. Phases 2–5 have local evidence.
Phase 6 packets 1–8 are implemented; wrapper acceptance is still pending.
Phase 7 packets 1–6 are specified (Stitch brief, API/UI map, Stitch treated as
a template not layout, component-system fallback) and await user acceptance
of the handoff. See
[docs/README.md](docs/README.md).
