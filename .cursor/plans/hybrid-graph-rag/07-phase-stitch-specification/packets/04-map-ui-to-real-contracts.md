---
phase: 7
packet: 4
status: pending
title: "Map each visible action and field to a real typed API/Auth contract; identify gaps instead of inventing mock behavior."
requirement_ids: [P07-04]
---

# Packet 4 — Map each visible action and field to a real typed API/Auth contract; identify gaps instead of inventing mock behavior.

Read the [Phase 7 shared contracts](../00-shared-contracts.md) and [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

- `P07-01` through `P07-03` provide verified inventory, screens, and state matrices.
- Generated/current Auth, OpenAPI, API-version, and SSE schemas are available.

## Allowed outputs

- Final `docs/frontend/API_UI_MAPPING.md`.
- Cross-links from the Stitch brief to verified mappings and unresolved gaps.
- Phase 7 mapping evidence.

## Forbidden outputs

- New application contracts, hidden client derivations, untyped payloads, or renamed server fields.
- Mock data or generated-frame labels presented as live diagnostics.
- Client guards presented as authorization enforcement.

## Ordered actions

1. Assign every visible field, action, status, diagnostic, recovery control, and transition to an exact Auth/API/SSE contract and source version.
2. Record request/event/response fields, actor/role, authoritative authorization boundary, loading/terminal behavior, idempotency key, sequence/reconnect rules, and sanitized error/fallback.
3. Map signed source access, restricted-read/download auditing, table provenance, citation/inference links, graph resolution, quotas, budgets, rate limits, and compatibility admission.
4. Trace each Stitch prompt/frame component to mapping rows and each mapping row back to a canonical screen/state.
5. Mark missing, ambiguous, incompatible, or security-sensitive contracts with owner, blocker, and required disposition.

## Acceptance checks

- Every visible element in `STITCH_BRIEF.md` has a verified mapping or explicit unresolved gap.
- Bearer POST submission, additive SSE events, minimum-client checks before paid work, ordered resume, cancellation, and one terminal state are represented.
- Mapping separates display convenience from server enforcement and canonical evidence from candidate/graph diagnostics.
- No gap is closed with a mock, placeholder, random value, or speculative endpoint.

## Negative tests

- Search the mapping for unmapped controls, fields without schema provenance, role claims without server denial, and diagnostics sourced only from generated HTML.
- Test duplicate submit, reconnect after sequence loss, unknown additive event, incompatible client, forged role, and unauthorized source access mappings.
- Reject direct browser access to private service credentials or internal trace payloads.

## Stop routes

- Stop when a visible requirement lacks a real typed contract or when repository behavior conflicts with security/data/cost/acceptance semantics.
- Assign the gap to its owning phase and block dependent approval.

## Required evidence

Append `P07-04` proof to [`docs/development/phase-07-stitch-specification-evidence.md`](../../../../../docs/development/phase-07-stitch-specification-evidence.md): bidirectional screen/mapping coverage, schema sources/versions, negative mapping tests, unresolved gaps/owners, and validation commands/results.
