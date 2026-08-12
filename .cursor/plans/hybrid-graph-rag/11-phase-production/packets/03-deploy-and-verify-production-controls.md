---
phase: 11
packet: 3
status: pending
title: "Run protected migrations and health-gated immutable deployment; verify CORS, redirects, origin restrictions, egress, Auth, budgets, rates, BM25 projection/recheck/fallback, and private services."
requirement_ids: [P11-03]
---

# Packet 3 — Run protected migrations and health-gated immutable deployment; verify CORS, redirects, origin restrictions, egress, Auth, budgets, rates, BM25 projection/recheck/fallback, and private services.

Required contracts: [phase shared](../00-shared-contracts.md) and [production delta](../../shared/release/04-production-promotion-delta.md).

## Preconditions

- P11-01/02 pass; exact expansion/images/Vercel/SSM/approval/secrets/health/drain/rollback and safe fixtures match Phase 10; access closed.

## Allowed outputs

- Protected expansion and blue/green deployment audit; bounded control checks; qualified abort/application rollback; evidence.

## Forbidden outputs

- Destructive/unapproved/mutable migration/image/schema rollback/runtime-create; user/bulk/destructive testing; CORS/origin/egress/private/Auth/budget/rate/BM25 bypass; drift.

## Ordered actions

1. Reverify hashes/approval/OIDC/SSM/secret path; run exact expansion.
2. Keep old API on expanded schema; start/health inactive, drain, switch, stop old only after success.
3. Deploy exact Vercel artifact and verify compatibility.
4. Check DNS/TLS/CORS/redirect/CSP/origin/direct origin/egress/private ports.
5. Check Auth/JWKS/Storage/RLS/budgets/rates.
6. Run bounded synthetic BM25 projection/typed query/recheck/stale rejection/dense+term fallback.

## Acceptance checks

- **P11-03-A:** Protected exact expansion, short-lived credentials, no contraction. Evidence: audit. Failure: stop/forward fix.
- **P11-03-B:** Old slot compatible; inactive health/drain/switch/abort safe. Evidence: timeline. Failure: abort.
- **P11-03-C:** DNS/TLS/CORS/origin/egress/private controls match. Evidence: matrix. Failure: access closed.
- **P11-03-D:** Auth/Storage/RLS/budget/rate/private services secure. Evidence: report. Failure: blocker.
- **P11-03-E:** Exact BM25 typed/rechecked/degraded path safe. Evidence: smoke. Failure: access closed.

## Negative tests

- Wrong migration/OIDC/SSM/destructive DDL; failed inactive health; unsupported client/CORS/redirect/origin; public/egress; token/budget/rate; stale BM25/unsafe query.

## Stop routes

- Stop on artifact/protected-path/old-slot/health/origin/egress/Auth/budget/rate/BM25/client failure; application rollback/forward fix only; access closed.

## Required evidence

Append P11-03 to `docs/development/phase-11-production-evidence.md`: approval/OIDC/SSM/migration, deployment timeline/artifacts, network/web controls, Auth/Storage/RLS/budget/rate, BM25 recheck/fallback, negatives, abort/rollback, repairs.
