---
phase: 8
packet: 66
status: pending
title: "Split UI controls and data-display CSS"
requirement_ids: [P08-66]
---

# Packet 66 — Split UI controls and data-display CSS

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `MOD-12` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-45 complete. ui.module.css is inspectable.

## Allowed outputs

ui/styles/controls.module.css and data-display.module.css plus owning component import updates.

## Forbidden outputs

Copying a selector into both old and new modules. Visual geometry changes.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Move button/input/select/form and table/pill/empty/error/status selectors. Each CSS module <=280. Update geometry/token tests.

## Acceptance checks

Geometry/design-token tests pass. No duplicated selectors.

## Negative tests

A visual snapshot update solely to hide a move fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a selector owner cannot be determined.

## Required evidence

Append `P08-66` (`MOD-12`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
