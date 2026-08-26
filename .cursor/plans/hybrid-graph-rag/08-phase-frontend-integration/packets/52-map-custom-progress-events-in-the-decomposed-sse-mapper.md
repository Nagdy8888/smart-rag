---
phase: 8
packet: 52
status: pending
title: "Map custom progress events in the decomposed SSE mapper"
requirement_ids: [P08-52]
---

# Packet 52 — Map custom progress events in the decomposed SSE mapper

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `BEP-05` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-32, P08-48, P08-50, and P08-51 complete.

## Allowed outputs

sse/mapping/progress.py, diagnostics.py stubs only as needed, mapper.py/status.py edits. query_sse_mapping.py remains <=100.

## Forbidden outputs

Regrowing the facade. Releasing draft text. Fabricating successful completion on cancel/error.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

node_start -> status running phase=started. Node update -> existing status plus completed/failed. tool_progress -> public event. Malformed/extra-key custom payloads drop with structured metadata logs. Hold drafts until verify_answer.

## Acceptance checks

Existing mapper/verified-final tests stay green. Malicious custom payloads emit nothing. Start precedes completed. No token_delta before verify.

## Negative tests

A query/result/error custom field appearing on the wire fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if verified-final hold would be weakened.

## Required evidence

Append `P08-52` (`BEP-05`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
