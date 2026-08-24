---
phase: 8
packet: 21
status: pending
title: "Run deterministic release gates"
requirement_ids: [P08-21]
---

# Packet 21 — Run deterministic release gates

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-20 quality contracts exist. No live provider is required in this packet.

## Allowed outputs

Format, lint, types, unit, contract, docs, frontend, OpenAPI, migrations, frontend build, deterministic Playwright, git diff --check, secret scan.

## Forbidden outputs

Claiming production-like verification. Using a fixture executor that injects token events as the production-executor proof. Printing secrets.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-21 — Run deterministic release gates

Purpose: isolate repeatable CPU/local checks from credentialed stack verification so failures are attributable and the weak-model run remains bounded.

Required checks:

- `uv run python scripts/check.py --tier format`
- `uv run python scripts/check.py --tier lint`
- `uv run python scripts/check.py --tier types`
- `uv run python scripts/check.py --tier unit`
- `uv run python scripts/check.py --tier contract`
- `uv run python scripts/check.py --tier docs`
- `uv run python scripts/check.py --tier frontend`
- `uv run python scripts/ci/check_openapi.py`
- `uv run python scripts/ci/check_migrations.py`
- `pnpm --filter smart-rag-frontend build`
- deterministic Playwright/component tests using approved synthetic/mock-provider inputs
- `git diff --check`
- repository secret/static-security scan that does not print secret values.

Acceptance:

- The production executor test binds a deterministic gateway and proves verified answer delivery; an SSE fixture that injects token events is insufficient.
- No mandatory skip, empty collection, zero-answer completion, migration drift, lint/type/build/docs failure, or secret finding is accepted.
- Record command, exit code, duration, and test count in evidence.
- Do not run the real provider or claim production-like verification in this packet.

## Acceptance checks

All listed deterministic commands pass. Production executor test uses a bound deterministic gateway.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop on skipped mandatory tests, empty collections, or secret findings. Do not run the real provider here.

## Required evidence

Append `P08-21` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
