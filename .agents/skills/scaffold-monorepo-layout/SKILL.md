---
name: scaffold-monorepo-layout
description: Scaffolds or restructures the approved uv/pnpm monorepo with separate LangGraph, FastAPI, worker, frontend, and shared-core boundaries. Use for repository initialization, workspace layout, package moves, import rewrites, or Docker/lockfile structure.
---

# Scaffold the Monorepo

Read the active Phase 1 wrapper and selected inline packet contract first. Read `prev_review/MONOREPO_RESTRUCTURE_PLAN.md` only for its deployable-separation method; never copy its PO/image-agent code, Airtable/GAS services, local uploads, dependencies, or historical assumptions.

## Target workspaces

- Python: `apps/agents`, `apps/backend`, `apps/worker`, `packages/core`
- Node: `apps/frontend`
- Single LangGraph project: `apps/agents/langgraph.json`
- Single root `uv.lock` and `pnpm-lock.yaml`

## Dependency direction

Declare direct distribution dependencies: `smart-rag-agents -> smart-rag-core`, `smart-rag-backend -> smart-rag-agents + smart-rag-core`, `smart-rag-worker -> smart-rag-agents + smart-rag-core`, `smart-rag-core -> no apps`, and `frontend -> HTTP/Supabase contracts`. Use the import pairs from the selected Phase 1 packet and matching root `{ workspace = true }` source entries.

Core ingestion owns framework-independent adapters/helpers; agents ingestion owns StateGraph orchestration; worker owns poll/claim/lease/heartbeat/reclaim/release. Worker passes durable Storage references, never local file paths; graph nodes fetch through the core gateway. Core owns registry/catalog logic while LangGraph node wrappers stay in agents. Backend routers call backend services and contain no domain/persistence logic.

Reject reverse imports, FastAPI under agents/core, queue SQL/lifecycle under backend/agents, graph nodes under core/worker, provider logic in routers, direct ParadeDB/LightRAG use outside core adapters, local upload persistence, and speculative shared packages.

## Workflow

1. Inspect the real repository; distinguish greenfield scaffolding from a move and never invent legacy paths.
2. Verify current uv workspace, pnpm workspace, LangGraph project, Python build-backend, and Docker APIs from pinned/current primary documentation.
3. Create the non-package root workspace and exact member distribution/import names, pinned Hatchling `src/` wheel targets, direct dependencies, scripts, and source entries from the selected Phase 1 packet.
4. Scaffold only the Phase 1 packet directories needed by the active work; use real health/import behavior, not placeholder success.
5. Configure one `langgraph.json` for query and ingestion `graph.py:graph` exports using the current verified LangGraph file-path contract.
6. Keep each deployable's settings/dependencies minimal; shared implementation goes into core only when at least two deployables use it.
7. Add architecture/import tests before moving or adding business logic.
8. Generate locks once from the root and fail CI on duplicate or stale lockfiles.
9. Build Python images from repository-root context. Copy all member metadata for resolution, then only required sources; run `uv sync --locked --package <distribution-name> --no-dev` and never create image-local lockfiles.
10. Validate local Compose paths, non-root application images, health checks, package entrypoints, and editable/workspace imports. Include private digest-pinned ParadeDB/`pg_search` with no public port, separate bootstrap/reader/writer credentials, hard resources, persistent development volume, and versioned `infra/paradedb` initialization/migration assets.

## Verification

Run locked Python/Node installs, import-boundary tests, Ruff/Pyright/pytest, ESLint/TypeScript/Vitest, production builds, LangGraph config loading, Docker image builds, Compose validation, ParadeDB extension/BM25 health contract, and startup health checks. Report any planned member, image, or external service that remains unverified.
