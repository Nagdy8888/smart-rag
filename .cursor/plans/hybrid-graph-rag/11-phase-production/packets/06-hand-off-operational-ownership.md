---
phase: 11
packet: 6
status: pending
title: "Hand off named ownership, escalation, RTO/RPO/growth triggers, graph pin/exit procedure, quarterly qualification work, and tested Hybrid-only disable path."
requirement_ids: [P11-06]
---

# Packet 6 — Hand off named ownership, escalation, RTO/RPO/growth triggers, graph pin/exit procedure, quarterly qualification work, and tested Hybrid-only disable path.

Required contracts: [phase shared](../00-shared-contracts.md), [sizing envelope](../../shared/release/05-sizing-envelope.md), and [documentation/handoff](../../shared/release/06-documentation-operational-handoff.md).

## Preconditions

- P11-01–05 pass; final routes/dashboards/runbooks/pins/limits/risks/retention/rollback published; named owners available; bounded disable window; access closed.

## Allowed outputs

- Signed owner/escalation/trigger handoff, engine pin/exit/rebuild records, tested BM25/graph disable evidence, quarterly reservation, final matrix/acceptance request.

## Forbidden outputs

- Unowned alert/trigger/risk/runbook/engine; paper-only disable; expanded topology/scale/engine; access/completion/check/lock before acceptance.

## Ordered actions

1. Assign owner/backup/severity/ack/escalation/runbook to every operational/billing alert.
2. Hand off four-hour RTO, 24-hour RPO, best-effort availability, 80% envelope, 70% resource, incident/business triggers.
3. Record exact ParadeDB/`pg_search`/BM25 and LightRAG pins, versions, limits, licensing, mapping/temporal/ETA/cost, deletion/rebuild, exit.
4. Reserve one to two engineer-days quarterly for qualification/drills/mapping/source-map review.
5. Execute BM25-outage dense+term with Supabase recheck.
6. Execute graph disable-to-Hybrid-only with visible safe behavior.
7. Trace wrapper Deliver/Review/Done; keep pending and request acceptance.

## Acceptance checks

- **P11-06-A:** Every alert/trigger/retention/provider/risk has named owner/escalation. Evidence: matrix. Failure: no access.
- **P11-06-B:** Exact capacity/trigger semantics create dated architecture review. Evidence: assertions. Failure: repair/Phase 10.
- **P11-06-C:** Complete engine pins/limits/exit/deletion/rebuild/quarterly reservation. Evidence: signed handoff. Failure: block.
- **P11-06-D:** BM25 degradation and graph disable are safe, visible, rechecked, and never graph-only answering. Evidence: execution. Failure: no access.
- **P11-06-E:** Final mandatory matrix passes; status pending until user acceptance. Evidence: matrix/plan. Failure: revert.

## Negative tests

- Remove owner/escalation; cross 80%/70% trigger; unpinned engine; stale BM25 during outage; relationship query with graph disabled; premature completion/access.

## Stop routes

- Stop on unowned/missing quarterly/pin/exit/unsafe degradation/stale/graph-only/missing gate/premature access; return material changes to Phase 10; no lock update.

## Required evidence

Finalize P11-06 in `docs/development/phase-11-production-evidence.md`: owner/trigger matrix, engine/version/index/workspace/limit/exit records, quarterly reservation, BM25/graph disable execution, final-gate traceability, go/no-go/access recommendation, acceptance request; keep pending.
