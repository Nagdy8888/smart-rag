---
phase: 7
packet: 1
status: pending
title: "Inventory real Phase 6 API, Auth, streaming, route-diagnostic, document, graph, tool, usage, and administration contracts."
requirement_ids: [P07-01]
---

# Packet 1 — Inventory real Phase 6 API, Auth, streaming, route-diagnostic, document, graph, tool, usage, and administration contracts.

Read the [Phase 7 shared contracts](../00-shared-contracts.md) and [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

- Phases 1–6 and their required sign-offs are complete.
- The Phase 6 thin authenticated UI and actual Auth/OpenAPI/SSE contracts are inspectable.
- Repository-defined contract-generation and validation commands are known.

## Allowed outputs

- Verified contract inventory and provenance in `docs/frontend/API_UI_MAPPING.md`.
- Explicit unresolved-gap entries and Phase 7 evidence.
- Documentation-only corrections within this packet's scope.

## Forbidden outputs

- Application code, schema, endpoint, event, or authorization changes.
- Mock endpoints, invented fields, static diagnostics, placeholder success, or inferred provider behavior.
- Production frontend implementation or design generation.

## Ordered actions

1. Inspect real Phase 2 Auth and Phase 6 API/OpenAPI/SSE/version-handshake contracts, generated types, authorization rules, and thin-UI behavior.
2. Inventory chat/diagnostics, documents/ingestion, graph, tables, tools/curation, team/admin, usage/budgets/rates, audit, profile, and company-settings contracts.
3. Record each contract's authoritative owner, typed fields, roles, request/event/response flow, idempotency/reconnect behavior, terminal/fallback states, and source path/version.
4. Cross-check every required canonical screen and state; mark absent or incompatible behavior as an unresolved owning-phase gap.

## Acceptance checks

- The inventory is traceable to repository files or generated contracts, not plan inference.
- Auth-provider-direct operations are distinguished from FastAPI-owned operations.
- API compatibility, paid-work admission, ordered SSE resume, cancellation, diagnostics, source access, and role enforcement are covered.
- Every canonical screen family has verified inputs or an explicit gap.

## Negative tests

- Reject any UI field or action lacking a real typed owner.
- Reject client-only authorization, browser exposure of privileged credentials, unverified BM25/graph text, and raw internal errors.
- Reject claims that FastAPI throttles browser-direct Supabase Auth operations.

## Stop routes

- Stop for an incomplete prerequisite, missing generated contract, unverifiable dependency, or security/data/cost/acceptance contradiction.
- Return backend contract gaps to their owning phase; do not solve them with frontend fiction.

## Required evidence

Append `P07-01` proof to [`docs/development/phase-07-stitch-specification-evidence.md`](../../../../../docs/development/phase-07-stitch-specification-evidence.md): inspected sources/versions, inventory coverage, validation commands/results, gap list, negative findings, and Phase 8 handoff impact.
