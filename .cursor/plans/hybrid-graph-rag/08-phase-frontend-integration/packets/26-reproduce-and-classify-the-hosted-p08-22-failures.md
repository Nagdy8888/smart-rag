---
phase: 8
packet: 26
status: pending
title: "Reproduce and classify the hosted P08-22 failures"
requirement_ids: [P08-26]
---

# Packet 26 — Reproduce and classify the hosted P08-22 failures

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `P08B-00` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-24 complete. Canonical P08-22 packet and hosted-runtime ADR are readable. Hosted credentials are optional; absence is BLOCKED not a fake pass.

## Allowed outputs

Redacted diagnosis evidence only. No production code changes.

## Forbidden outputs

Hosted resets, printing secrets, mock-model hosted proof, or application edits.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Verify prerequisites without printing values. If the hosted stack can start, run one bounded real-provider Ask and record only non-secret run ID, event type/sequence/status, terminal, assistant row count, usage row count, and migration names. Classify schema parity, settlement, terminal sync, and verify visibility as PASS|FAIL|BLOCKED.

## Acceptance checks

A redacted classification record exists. Missing credentials are recorded as BLOCKED. No production code changed.

## Negative tests

Using mock-model mode as hosted proof fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop and mark BLOCKED when Docker, hosted credentials, schema access, or provider budget are unavailable.

## Required evidence

Append `P08-26` (`P08B-00`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
