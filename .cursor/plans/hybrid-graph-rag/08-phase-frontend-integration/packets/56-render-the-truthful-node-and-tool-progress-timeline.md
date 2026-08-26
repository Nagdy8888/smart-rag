---
phase: 8
packet: 56
status: pending
title: "Render the truthful node and tool progress timeline"
requirement_ids: [P08-56]
---

# Packet 56 — Render the truthful node and tool progress timeline

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `FEP-02` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-55 complete.

## Allowed outputs

run-progress-timeline.tsx and AnswerSurface composition. Keep runStatusLine during migration then remove the competing status surface.

## Forbidden outputs

Fake percentages, elapsed time, or phantom stages. Unsafe HTML for keys.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Render only reducer items. Friendly labels with raw keys in details. Active started row has spinner and aria-current=step. Collapse after reveal completion. Copy: current stage; Verified — preparing display; Verifying labels from verify_answer; terminal uses existing safe failure copy.

## Acceptance checks

Company fixture shows only emitted stages. General fixture has no company retrieval/tool rows. No assistant prose before verified token. Keyboard expand/collapse works.

## Negative tests

A client-created timestamp or percentage fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if two competing status surfaces would remain at integration end.

## Required evidence

Append `P08-56` (`FEP-02`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
