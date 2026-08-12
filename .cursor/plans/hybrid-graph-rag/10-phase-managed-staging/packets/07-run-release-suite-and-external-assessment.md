---
phase: 10
packet: 7
status: pending
title: "Run the complete release suite and an independent external security assessment with synthetic/redacted data and no long-lived CI or runtime bootstrap credential."
requirement_ids: [P10-07]
---

# Packet 7 — Run the complete release suite and an independent external security assessment with synthetic/redacted data and no long-lived CI or runtime bootstrap credential.

Required contracts: [phase shared](../00-shared-contracts.md), [managed gates](../../shared/release/02-managed-gates.md), and [staging topology](../../shared/release/03-staging-topology.md).

## Preconditions

- P10-01–06 evidence exists for one topology; every gate maps to evidence; assessor scope/authorization/redaction/retest is approved.

## Allowed outputs

- Complete no-skip staging suite, independent assessment/retest, remediation/reruns, final managed matrix, Phase 11 manifest, acceptance request.

## Forbidden outputs

- Production data/destructive scope; skipped/empty/fake assessment; long-lived credentials; open Critical/High; unowned Medium; completion/check/lock/promotion.

## Ordered actions

1. Trace P10-01–06 to wrapper Deliver/Review/Done.
2. Run complete PR/merge/nightly/release/security/eval/load/restore/IaC/policy/stream/rotation/alert/rollback suite with nonzero tests.
3. Assess Auth/JWKS, RLS/ACL/identity, private BM25/query/recheck, signed URL/quarantine, SSRF/egress, injection, origin bypass, rate ownership, Storage.
4. Remediate/retest Critical/High; accept Medium only with dated ADR/owner.
5. Rerun affected gates; produce exact Phase 11 promotion manifest/deltas/risks/rollback; keep pending.

## Acceptance checks

- **P10-07-A:** Complete synthetic/redacted production-equivalent suite passes with no skipped/empty/stale/zero-test gate. Evidence: matrix. Failure: no-go.
- **P10-07-B:** No long-lived credential/public service/mutable ParadeDB/unapproved migration. Evidence: custody/IaC report. Failure: blocker.
- **P10-07-C:** Full independent scope has zero open Critical/High and owned dated Medium. Evidence: redacted report/retest. Failure: stop.
- **P10-07-D:** One exact artifact set proves all managed gates. Evidence: traceability. Failure: rerun.
- **P10-07-E:** Promotion inputs recorded; status pending until acceptance. Evidence: manifest/plan. Failure: revert.

## Negative tests

- Zero/skip/stale/digest drift; credential search; unauthorized/production assessment; open finding/unowned risk; unqualified production delta.

## Stop routes

- Stop on any failed/unrun gate, production contamination, exposure, finding, risk, drift, or delta; rotate/investigate; no completion/lock update.

## Required evidence

Finalize P10-07 in `docs/development/phase-10-managed-staging-evidence.md`: identities, complete matrix/counts, synthetic proof, custody report, redacted assessment/retest/ADRs, reruns, final-gate traceability, promotion/rollback manifest, acceptance request; keep pending.
