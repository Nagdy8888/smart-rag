---
phase: 8
packet: 39
status: pending
title: "Align revoked-session contract and remove effect mirroring"
requirement_ids: [P08-39]
---

# Packet 39 — Align revoked-session contract and remove effect mirroring

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `SEC-02` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-25 complete. Backend identity dependency and frontend error classifier are inspectable.

## Allowed outputs

identity.py detail session_revoked, frontend compatibility alias, chat-app /me failure derivation, and focused tests.

## Forbidden outputs

Exposing raw backend detail, loosening the safe-detail validator, or disabling react-hooks/set-state-in-effect.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Change authorization detail from 'Session revoked' to session_revoked. Keep a narrow alias for both values. Derive meFailure from query data/error instead of setFailure in an effect. Preserve the safe banner and sign-out path.

## Acceptance checks

Both spellings classify as session_revoked. Arbitrary human detail stays sanitized. ESLint no longer reports set-state-in-effect for /me. Auth contract tests pass.

## Negative tests

Rendering raw backend sentences or disabling the lint rule fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if the backend detail is used as user-visible HTML.

## Required evidence

Append `P08-39` (`SEC-02`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
