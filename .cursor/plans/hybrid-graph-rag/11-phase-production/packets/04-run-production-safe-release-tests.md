---
phase: 11
packet: 4
status: pending
title: "Run production-safe smoke, security, redaction, API handshake, BM25 projection/query/degradation, audit-anchor/export, OpenAI/AWS/Supabase alert delivery, database/Storage consistency, backup-health, and rollback tests before user access."
requirement_ids: [P11-04]
---

# Packet 4 — Run production-safe smoke, security, redaction, API handshake, BM25 projection/query/degradation, audit-anchor/export, OpenAI/AWS/Supabase alert delivery, database/Storage consistency, backup-health, and rollback tests before user access.

Required contracts: [phase shared](../00-shared-contracts.md) and [production delta](../../shared/release/04-production-promotion-delta.md).

## Preconditions

- P11-01–03 pass; approved bounded synthetic fixtures/redaction/alarms/backup-consistency/anchor/rollback; no destructive production action; on-call active; access closed.

## Allowed outputs

- Bounded production-safe smoke/security/redaction/compatibility/BM25/audit/alert/consistency/backup/rollback evidence.

## Forbidden outputs

- Private disclosure; destructive restore/failover/load/penetration; staging recreation with private data; raw secrets/content; access with failed/unrun gate; unsafe schema rollback.

## Ordered actions

1. Reconfirm identities/scope/abort/access hold.
2. Run bounded network/Auth/Storage/RLS/role/budget/rate/email/API smoke.
3. Verify production trace/log redaction.
4. Exercise synthetic BM25 typed query/recheck/stale rejection/health/lag/degradation.
5. Export/verify anchors and missing/invalid detection non-destructively.
6. Send bounded real alarm-route signals; verify database/Storage consistency and backup/PITR health.
7. Exercise application rollback/old-slot/forward-fix; reconcile fixtures/state.

## Acceptance checks

- **P11-04-A:** All bounded smoke/security/compatibility controls pass. Evidence: matrix. Failure: access closed.
- **P11-04-B:** Traces/logs/evidence redact source/secrets. Evidence: assertions. Failure: blocker/incident.
- **P11-04-C:** BM25 exact pin/query/recheck/degradation safe. Evidence: report. Failure: access closed.
- **P11-04-D:** Real operational/audit/BM25/billing/queue/graph/database/Storage/backup routes deliver/ack. Evidence: matrix. Failure: repair.
- **P11-04-E:** Consistency/backup/old-slot/application rollback/forward-fix pass. Evidence: report. Failure: no-go.

## Negative tests

- Unsupported client/invalid role/origin/egress/stale BM25/rate/budget; sensitive marker; broken alert; synthetic mismatch; failed slot; blocked destructive action.

## Stop routes

- Stop/access closed on security/redaction/compatibility/stale evidence/alarm/consistency/backup/rollback failure; incident on exposure; Phase 10 on drift.

## Required evidence

Append P11-04 to `docs/development/phase-11-production-evidence.md`: identities/scope, smoke/redaction/API/BM25/anchor/alarm/consistency/backup/rollback, reconciliation, negatives, repairs, access decision.
