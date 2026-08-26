---
phase: 8
packet: 70
status: pending
title: "Split document detail and import tabs"
requirement_ids: [P08-70]
---

# Packet 70 — Split document detail and import tabs

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-17` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-63 complete.

## Allowed outputs

use-document-detail.ts, import-file-tab.tsx, import-website-tab.tsx, reuse of document-delete-sheet.tsx, and import-source-sheet.test.tsx.

## Forbidden outputs

Leaking 404 titles. Changing handshake/attestation or visibility-aware polling.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Keep controlled form state unchanged. Add a direct import-source-sheet test.

## Acceptance checks

Library and new import-sheet tests pass.

## Negative tests

A 404 title leak fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if delete-sheet reuse would change confirmation copy unexpectedly.

## Required evidence

Append `P08-70` (`MOD-17`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
