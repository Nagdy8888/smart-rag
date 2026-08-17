---
phase: 9
packet: 5
status: complete
title: "Kill, deny, fill, and restart worker/ParadeDB/Valkey/services to prove reclaim, degraded retrieval/rate behavior, heartbeat/reconnect, and safe recovery."
requirement_ids: [P09-05]
---

# Packet 5 — Kill, deny, fill, and restart worker/ParadeDB/Valkey/services to prove reclaim, degraded retrieval/rate behavior, heartbeat/reconnect, and safe recovery.

Required contracts: [phase shared](../00-shared-contracts.md) and [local release gates](../../shared/release/01-local-release-gates.md).

## Preconditions

- P09-01–04 pass; isolated local fault/reset paths and observable leases/checkpoints/outbox/index/graph/rate/budget/events exist.

## Allowed outputs

- Local fault/reclaim/replay/reconnect/recovery reports; bounded retry/health/fallback fixes; runbook/evidence updates.

## Forbidden outputs

- Managed/production faults; unbounded retry; fake health; stale evidence; double admission/paid work; Valkey/ParadeDB authority; security bypass.

## Ordered actions

1. Record baseline authoritative and derived state.
2. Kill worker during each durable stage and verify lease/checkpoint resume.
3. Kill/version-mismatch ParadeDB; verify dense+term degradation, recheck, replay, and recovery.
4. Kill/restart/ACL-deny/fill each Valkey independently; verify fail-closed/fallback/alerts/no double admission.
5. Restart services during five streams; verify heartbeat, disconnect, sequenced resume, cancellation, idempotency, deadlines.
6. Reconcile pre/post canonical, budget, job, graph, BM25, rate, cache, and audit state.

## Acceptance checks

- **P09-05-A:** Worker reclaim/resume creates no duplicate canonical/derived/paid work. Evidence: before/after ledger. Failure: blocker.
- **P09-05-B:** ParadeDB faults visibly degrade with zero stale/unauthorized evidence and recover active index. Evidence: fault report. Failure: stop.
- **P09-05-C:** Valkey faults preserve ownership/fail-closed semantics and no double admission. Evidence: fault matrix. Failure: blocker.
- **P09-05-D:** SSE resumes monotonically with one paid run and deadline termination. Evidence: event timeline. Failure: stop.
- **P09-05-E:** Post-recovery state reconciles without hidden loss/authority transfer. Evidence: diff. Failure: repair.

## Negative tests

- Restart around lease expiry; inject stale/wrong-index BM25 IDs; deny/exhaust Valkey; replay one idempotency key; remove a checkpoint/dependency.

## Stop routes

- Stop on duplicate work, overspend, stale/unauthorized evidence, rate bypass, unbounded retry, heartbeat/deadline failure, or unreconciled state.
- Leave managed-host/CDN faults for Phase 10.

## Required evidence

Append P09-05 to `docs/development/phase-09-local-release-candidate-evidence.md`: baseline, fault matrix/commands/timelines, authoritative diffs, BM25/Valkey degradation, alerts, bounds, durations, negative tests, repairs, and reconciliation.
