---
phase: 10
packet: 6
status: pending
title: "Perform and record database-plus-Storage restore/reconciliation followed by clean BM25 projection rebuild, instance rebuild, old-slot/new-schema and frontend/API deploy-skew behavior, failed deployment, forward-fix migration boundary, and application rollback."
requirement_ids: [P10-06]
---

# Packet 6 — Perform and record database-plus-Storage restore/reconciliation followed by clean BM25 projection rebuild, instance rebuild, old-slot/new-schema and frontend/API deploy-skew behavior, failed deployment, forward-fix migration boundary, and application rollback.

Required contracts: [phase shared](../00-shared-contracts.md), [managed gates](../../shared/release/02-managed-gates.md), [staging topology](../../shared/release/03-staging-topology.md), and [sizing envelope](../../shared/release/05-sizing-envelope.md).

## Preconditions

- P10-01–05 pass; managed recovery point, full inventory, reconciliation/rebuild/instance/blue-green/skew/rollback runbooks, old/new artifacts and expansion hash are frozen.

## Allowed outputs

- Managed restore/reconciliation, BM25/instance rebuild, deploy-skew/failure/drain/rollback/forward-fix, duration, and sizing evidence.

## Forbidden outputs

- Production restore; ParadeDB canonical snapshot; pre-reconciliation rebuild; destructive contract DDL/schema rollback; artifact drift; missing bucket/orphan/stale/client failure hidden.

## Ordered actions

1. Record recovery point and all schema/LightRAG/mapping/outbox/index/bucket inventory.
2. Restore database and all four durable buckets; reconcile orphans/missing/hash mismatch with exclusion/alerts.
3. Destroy/rebuild ParadeDB only from reconciled authorized current Supabase; parity/time.
4. Rebuild EC2 from IaC/images/secrets with empty ParadeDB; verify service health.
5. Run old API on expansion, both frontend/API orders, unsupported-client behavior.
6. Force inactive-slot/deploy failure; prove old active, application rollback, forward-fix boundary.

## Acceptance checks

- **P10-06-A:** Complete managed restore at recorded point. Evidence: inventory. Failure: blocker.
- **P10-06-B:** Reconciliation marks/quarantines/excludes/alerts before rebuild. Evidence: adversarial report. Failure: stop.
- **P10-06-C:** Authoritative-only empty BM25 rebuild reaches parity/time with no canonical snapshot. Evidence: lineage. Failure: blocker/sizing.
- **P10-06-D:** Instance rebuild meets approved RTO/RPO. Evidence: timed report. Failure: revise/stop.
- **P10-06-E:** Old-slot/schema, both deploy orders, failure, drain, rollback, forward-fix pass without contraction. Evidence: matrix. Failure: requalify.

## Negative tests

- Missing bucket/object/hash/orphan; snapshot-only recovery; stale BM25; destructive DDL; incompatible clients; failed inactive slot/SSM deploy.

## Stop routes

- Stop on restore/reconciliation/parity/RTO/RPO/instance/DDL/skew/rollback failure; changed artifact/plan invalidates proof; use forward fix.

## Required evidence

Append P10-06 to `docs/development/phase-10-managed-staging-evidence.md`: recovery/inventory, reconciliation, rebuild lineage/parity/time, instance timeline, deployment matrix/failure/drain/rollback/forward-fix, RTO/RPO, negatives, repairs.
