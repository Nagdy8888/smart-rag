---
phase: 8
packet: 45
status: pending
title: "Make ChatApp composition-only and enforce frontend budgets"
requirement_ids: [P08-45]
---

# Packet 45 — Make ChatApp composition-only and enforce frontend budgets

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-06` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-40 through P08-44 complete.

## Allowed outputs

Optional chat-workspace, chat-banners, use-conversation-actions, use-chat-selection, and architecture-budget.test.ts.

## Forbidden outputs

Progress/reveal behavior. Fetch/SSE/retry/pagination/modal-focus/reveal scheduling in chat-app.tsx.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Reduce chat-app.tsx to <=300 physical lines of composition. Enforce api.ts/types.ts <=100, new modules <=300, no consumeSse/fetch in ChatApp, exactly one consumeSse owner.

## Acceptance checks

architecture-budget and chat-app tests pass. Lint and typecheck pass.

## Negative tests

A second SSE consumer fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if behavior tests fail during extraction. Do not add progress code to pass tests.

## Required evidence

Append `P08-45` (`MOD-06`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
