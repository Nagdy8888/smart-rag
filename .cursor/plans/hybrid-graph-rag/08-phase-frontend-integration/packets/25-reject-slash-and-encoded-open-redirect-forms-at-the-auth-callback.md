---
phase: 8
packet: 25
status: pending
title: "Reject slash and encoded open-redirect forms at the auth callback"
requirement_ids: [P08-25]
---

# Packet 25 — Reject slash and encoded open-redirect forms at the auth callback

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `SEC-01` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-24 integrity passed. Current auth callback route is inspectable.

## Allowed outputs

apps/frontend/src/app/(auth)/auth/callback/route.ts, safe-next-path.ts, and safe-next-path.test.ts.

## Forbidden outputs

Client-side checks described as the security gate. Weakening PKCE or anon-client exchange. Broad auth refactors.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Extract safeNextPath(raw, requestOrigin) that returns / unless the decoded value is a same-origin root-relative path. Reject absolute URLs, //, any backslash, encoded slash/backslash ambiguity, control characters, userinfo, and a parsed origin different from requestOrigin. Preserve valid path, query, and fragment only after same-origin parsing.

## Acceptance checks

Every invalid matrix case redirects to /. Every valid case remains on the request origin. Focused vitest, lint, and typecheck pass.

## Negative tests

https://evil.example, //evil.example, /\evil.example, /\\evil.example, %2f%2fevil.example, /%5cevil.example, mixed-case encodings, CR/LF, and malformed percent encoding must become /.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

If URL normalization differs between the pinned Node runtime and tests, add runtime contract cases; do not weaken validation.

## Required evidence

Append `P08-25` (`SEC-01`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
