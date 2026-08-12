---
phase: 9
packet: 6
status: pending
title: "Run local egress enforcement, dependency/image scans, Supabase database plus all Storage-bucket restore/reconciliation including LightRAG, clean ParadeDB projection rebuild, and instance-equivalent sizing evidence."
requirement_ids: [P09-06]
---

# Packet 6 — Run local egress enforcement, dependency/image scans, Supabase database plus all Storage-bucket restore/reconciliation including LightRAG, clean ParadeDB projection rebuild, and instance-equivalent sizing evidence.

Required contracts: [phase shared](../00-shared-contracts.md), [local release gates](../../shared/release/01-local-release-gates.md), and [sizing envelope](../../shared/release/05-sizing-envelope.md).

## Preconditions

- P09-01–05 pass; local egress/scanners/backup/restore/reconciliation/rebuild/sizing tools and frozen recovery fixtures exist.

## Allowed outputs

- Egress, SBOM/scan, database+Storage restore/reconciliation, clean BM25 rebuild/parity, recovery-duration, and instance-equivalent sizing reports.

## Forbidden outputs

- Cloud/production restore; ParadeDB as canonical backup; database-only restore; pre-reconciliation rebuild; ignored critical finding; local-as-managed claim.

## Ordered actions

1. Test parser/OCR/ParadeDB/API/agent/worker/proxy/Valkey/metadata egress boundaries.
2. Run secret/dependency/license/SBOM/Trivy scans on exact digests.
3. Back up and restore all application/private schemas, canonical/mapping/LightRAG/BM25 outbox/index state, and all durable buckets.
4. Quarantine object-only orphans; mark missing/hash-mismatched references unavailable; exclude/alert.
5. Destroy ParadeDB; rebuild only from reconciled authorized current Supabase; compare parity and time.
6. Consolidate EC2-equivalent resource and RTO/RPO sizing without managed proof.

## Acceptance checks

- **P09-06-A:** Egress policy denies prohibited/private/metadata paths. Evidence: matrix/logs. Failure: blocker.
- **P09-06-B:** Exact images/dependencies have no unresolved launch-blocking finding. Evidence: digest-bound reports. Failure: rebuild.
- **P09-06-C:** Database and every required bucket restore, including LightRAG/mappings/outbox/index. Evidence: inventory. Failure: blocker.
- **P09-06-D:** Reconciliation precedes authoritative-only BM25 rebuild and sampled parity. Evidence: lineage/parity. Failure: stop.
- **P09-06-E:** Local sizing/RTO/RPO produces signed repair/isolate/resize/reduce/stop decision. Evidence: report. Failure: sizing ladder.

## Negative tests

- Attempt prohibited egress; restore missing/orphan/hash fixtures; offer ParadeDB snapshot as authority; inject stale rebuilt rows; use digest with critical finding.

## Stop routes

- Stop on egress, scan, bucket, reconciliation, lineage, parity, or RTO/RPO failure.
- Leave managed restore/KMS/EC2/provider proof for Phase 10.

## Required evidence

Append P09-06 to `docs/development/phase-09-local-release-candidate-evidence.md`: egress/scan artifacts, recovery point/inventory, reconciliation fixtures, rebuild lineage/parity/durations, RTO/RPO/resource model, signed sizing decision, repairs, and managed handoff.
