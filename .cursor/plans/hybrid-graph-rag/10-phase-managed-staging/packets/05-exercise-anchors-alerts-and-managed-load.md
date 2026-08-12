---
phase: 10
packet: 5
status: pending
title: "Exercise staging KMS/S3 Object Lock audit anchors, OpenAI/AWS/Supabase billing and operational alarm routing, SES/OAuth/Storage, managed pooling, load, and database pressure."
requirement_ids: [P10-05]
---

# Packet 5 — Exercise staging KMS/S3 Object Lock audit anchors, OpenAI/AWS/Supabase billing and operational alarm routing, SES/OAuth/Storage, managed pooling, load, and database pressure.

Required contracts: [phase shared](../00-shared-contracts.md), [managed gates](../../shared/release/02-managed-gates.md), [staging topology](../../shared/release/03-staging-topology.md), and [sizing envelope](../../shared/release/05-sizing-envelope.md).

## Preconditions

- P10-01–04 pass; KMS/Object Lock, monitoring/billing, SES/OAuth/Storage, pooling/load telemetry, named routes, and bounded synthetic triggers are configured.

## Allowed outputs

- Anchor/mutation, alarm delivery, managed integration/load/database/resource, and signed sizing evidence.

## Forbidden outputs

- Production recipients/data/unbounded spend; mutable anchor proof; unproven/unowned alert; replica without primary recheck; artifact drift.

## Ordered actions

1. Export/anchor audit chain and test mutation/removal/reorder/fork/missing/invalid anchors.
2. Trigger bounded operational plus OpenAI/AWS/Supabase billing alarms and verify owner/ack/escalation/runbook.
3. Exercise SES sandbox, OAuth, Auth/Storage/signed URLs/CORS/CSP.
4. Run session/transaction pooling, direct migration path, caps/timeouts, CPU/IO/cache/slow-query pressure.
5. Run EC2/ParadeDB/Valkey/graph/OCR load and 70% maintenance triggers.
6. Reject replica unless primary ACL/current-version revalidation; decide envelope.

## Acceptance checks

- **P10-05-A:** Valid immutable anchor verifies; all tampering fails. Evidence: report. Failure: blocker.
- **P10-05-B:** Every operational/billing alarm reaches named route/ack/escalation. Evidence: matrix. Failure: repair.
- **P10-05-C:** SES/OAuth/Storage/Auth pass synthetically without exposure. Evidence: integration report. Failure: blocker.
- **P10-05-D:** Pool/database pressure and 70% isolation meet gates with authority intact. Evidence: telemetry. Failure: sizing route.
- **P10-05-E:** Real managed resources meet or resize/isolate/reduce/re-sign envelope. Evidence: report. Failure: stop.

## Negative tests

- Tamper anchors; break routes; unauthorized email/OAuth/Storage; saturate pools; stale replica; bounded spend alarm/overspend rejection.

## Stop routes

- Stop on anchor, alert, recipient, Auth/Storage/OAuth, pool, recheck, spend, or envelope failure; requalify changed topology/plan.

## Required evidence

Append P10-05 to `docs/development/phase-10-managed-staging-evidence.md`: anchor identities/adversarial results, full alarm matrix, integration results, pool/database/resource telemetry, triggers/replica/budgets, signed sizing, repairs.
