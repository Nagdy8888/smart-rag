---
phase: 8
packet: 8
status: pending
title: "Restore query runtime connectivity and deterministic readiness"
requirement_ids: [P08-08]
---

# Packet 8 — Restore query runtime connectivity and deterministic readiness

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-07 evidence is committed. Current settings, Compose, Docker, and readiness files are inspectable.

## Allowed outputs

DSN fail-fast, Compose injection, readiness probe, Dockerignore, frontend build-arg wiring, tests, docs.

## Forbidden outputs

Disabling prepared statements to keep a transaction-pooler checkpoint DSN. Committing hosts, passwords, or tokens. Reading or copying ignored local credential files into the repo.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-08 — Restore query runtime connectivity and deterministic readiness

Purpose: remove the database/configuration failure that currently prevents all model calls and make deployment configuration reproducible without hidden local files.

Primary files:

- [`packages/core/src/smart_rag_core/settings/backend.py`](packages/core/src/smart_rag_core/settings/backend.py)
- [`apps/agents/src/smart_rag_agents/query/store.py`](apps/agents/src/smart_rag_agents/query/store.py)
- [`apps/agents/src/smart_rag_agents/ingestion/checkpointer.py`](apps/agents/src/smart_rag_agents/ingestion/checkpointer.py)
- [`apps/backend/src/smart_rag_api/services/readiness.py`](apps/backend/src/smart_rag_api/services/readiness.py)
- [`docker-compose.yml`](docker-compose.yml)
- [`apps/frontend/Dockerfile`](apps/frontend/Dockerfile)
- [`.env.example`](.env.example), a new root [`.dockerignore`](.dockerignore), configuration docs, and focused settings/readiness tests.

Implementation:

- Preserve `SUPABASE_DB_URL` for short API transactions. Add explicit Compose injection for the already-defined `LANGGRAPH_CHECKPOINT_URL` and the existing `LIGHTRAG_DB_URL`; do not reuse a transaction-pooler DSN for long-lived LangGraph/LightRAG sessions.
- Fail fast with a sanitized configuration error when a known transaction-pooler DSN is supplied to a session/direct-only integration. Do not “fix” this by disabling prepared statements and continuing on the wrong pool mode.
- Keep local direct/session defaults compatible with the local Supabase port. Hosted values remain secret environment inputs; never commit hosts, usernames, passwords, or tokens.
- Add a bounded startup/readiness probe that opens the actual LangGraph saver/store connection, applies the correct role/schema, and closes cleanly. Readiness must distinguish core query availability from optional graph degradation.
- `query_ready=true` when the core Hybrid query path, durable run store/checkpointer, and model gateway prerequisites are usable. Missing LightRAG may produce a typed degraded dependency and later Hybrid fallback; it must not falsely make all chat unusable if the approved Hybrid fallback is healthy.
- Ensure frontend public configuration is passed explicitly at image build time. Add Docker build arguments for the public API base, Supabase URL, and publishable/anon key; runtime-only environment variables must not be assumed to rewrite already-built Next.js bundles.
- Add `.dockerignore` entries for `.env*`, `.git`, `.next`, `node_modules`, test reports, local plans/state, and other secrets/artifacts, while allowing tracked examples needed by the build.
- Do not read, print, commit, or copy the current local credential-like Vercel token. Record that the operator should rotate it if it was ever exposed outside the ignored local file.
- Keep readiness bounded below the browser timeout or raise the typed frontend timeout to a documented value with abort behavior; do not allow an unbounded health request.

Acceptance tests:

- A transaction-pooler checkpoint DSN fails before a paid run is admitted and without leaking the DSN.
- A direct/session checkpoint DSN opens the pinned saver and store successfully.
- `/health/ready` returns a stable result inside the documented timeout.
- Core healthy plus LightRAG unavailable reports degraded-but-query-capable Hybrid behavior, not fake graph readiness.
- Clean Docker build succeeds without `apps/frontend/.env.local` in the context.
- Image inspection/source tests prove no `.env.local`, privileged key, or Vercel token entered a layer.

## Acceptance checks

Transaction-pooler checkpoint DSN fails closed. Direct/session DSN opens saver/store. Ready probe is bounded. Clean Docker build excludes `.env.local`.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a required session DSN cannot be distinguished from the transaction pooler without guessing undocumented flags.

## Required evidence

Append `P08-08` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
