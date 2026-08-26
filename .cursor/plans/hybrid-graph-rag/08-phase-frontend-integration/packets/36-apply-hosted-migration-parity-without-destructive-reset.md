---
phase: 8
packet: 36
status: pending
title: "Apply hosted migration parity without destructive reset"
requirement_ids: [P08-36]
---

# Packet 36 — Apply hosted migration parity without destructive reset

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `P08B-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-26 classification exists. P08-27 through P08-35 complete. Explicit user approval required before any remote apply.

## Allowed outputs

Hosted apply of missing repository-order migrations after approval. Local migration/OpenAPI checks. Evidence of names/versions.

## Forbidden outputs

Editing applied migrations, resetting hosted Supabase, printing DSNs/keys, or repairing settlement/UI in this packet.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Compare repository ledger with hosted list_migrations. Inspect missing migrations and rollback/forward-fix implications. Apply only with explicit approval. Verify health/readiness and role/RLS advisors.

## Acceptance checks

Hosted migration names equal the ledger, or the packet is BLOCKED with missing names and no silent skip-pass.

## Negative tests

A destructive reset or edited applied migration fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if apply fails; write a forward-repair plan. Stop without approval.

## Required evidence

Append `P08-36` (`P08B-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
