---
phase: 10
packet: 4
status: pending
title: "Exercise asymmetric JWKS rollover, dual origin-secret rotation, real 50-second CDN SSE heartbeat/disconnect/resume, ParadeDB outage/version mismatch/rebuild, and Valkey degraded modes."
requirement_ids: [P10-04]
---

# Packet 4 — Exercise asymmetric JWKS rollover, dual origin-secret rotation, real 50-second CDN SSE heartbeat/disconnect/resume, ParadeDB outage/version mismatch/rebuild, and Valkey degraded modes.

Required contracts: [phase shared](../00-shared-contracts.md), [managed gates](../../shared/release/02-managed-gates.md), and [staging topology](../../shared/release/03-staging-topology.md).

## Preconditions

- P10-01–03 pass; managed JWKS, dual origin acceptance, 90-second assertions, BM25 rebuild/versioning, split Valkey, and reviewed runbooks are observable.

## Allowed outputs

- JWKS/origin rotation, real CDN stream, ParadeDB degradation/rebuild/parity, Valkey fault/recovery, and reconciliation evidence.

## Forbidden outputs

- Production secrets/data; HS256/auth outage; >15-minute origin overlap/zero valid secret; local-only stream; stale BM25; rate bypass; derived authority.

## Ordered actions

1. Exercise managed standby→active→retired JWKS with valid/revoked/stale/unknown sessions.
2. Rotate origin old+new, CloudFront switch/deploy, direct-origin check, old removal ≤15 minutes, abort/rollback.
3. Run real 50-second CDN SSE heartbeat/disconnect/resume/cancel/deadline.
4. Kill/version-mismatch ParadeDB; prove degradation/recheck/replay/recovery; clean rebuild/parity.
5. Kill/restart/ACL-deny/fill each Valkey; prove fail-closed/fallback/alerts/no double admission.
6. Reconcile state.

## Acceptance checks

- **P10-04-A:** JWKS rollover preserves valid sessions/rejects revoked/unknown with no HS256/outage. Evidence: timeline. Failure: blocker.
- **P10-04-B:** Origin rotation/rollback keeps one valid secret, rejects direct origin, overlap ≤15 minutes. Evidence: audit. Failure: restore/stop.
- **P10-04-C:** Real 50-second stream passes under 90-second settings with one paid run. Evidence: E2E timeline. Failure: blocker.
- **P10-04-D:** ParadeDB faults yield zero stale/unauthorized evidence and rebuild parity. Evidence: report. Failure: stop.
- **P10-04-E:** Valkey faults preserve fail-closed ownership/no double admission. Evidence: matrix. Failure: blocker.

## Negative tests

- Unknown/retired/HS256 tokens; early/late/failed origin switch; disabled heartbeat/replay; stale/wrong-index BM25; Valkey ACL/OOM/multi-worker recovery.

## Stop routes

- Stop on Auth/secret/origin/stream/idempotency/BM25/parity/rate failure; rotate exposure; rerun topology after material change.

## Required evidence

Append P10-04 to `docs/development/phase-10-managed-staging-evidence.md`: JWKS and origin timelines, overlap/rollback, CDN events/timeouts, ParadeDB fault/rebuild/parity, Valkey matrix, alerts/reconciliation, negatives, repairs.
