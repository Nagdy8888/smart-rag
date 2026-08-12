---
phase: 9
packet: 3
status: pending
title: "Measure Hybrid/Combined/table/inspection quality, BM25 projection/query/recheck/rebuild behavior, p50/p95/deadlines, model calls/cost, graph survival, writer throughput, and onboarding ETA."
requirement_ids: [P09-03]
---

# Packet 3 — Measure Hybrid/Combined/table/inspection quality, BM25 projection/query/recheck/rebuild behavior, p50/p95/deadlines, model calls/cost, graph survival, writer throughput, and onboarding ETA.

Required contracts: [phase shared](../00-shared-contracts.md), [local release gates](../../shared/release/01-local-release-gates.md), and [sizing envelope](../../shared/release/05-sizing-envelope.md).

## Preconditions

- P09-01/02 pass for one candidate; signed targets, frozen profiles, immutable holdout, labels, harness, sample/warmup/cache/concurrency rules are fixed.

## Allowed outputs

- Machine-readable per-language/query-class quality, retrieval, BM25, latency, call/cost, graph, throughput, ETA, and signed envelope reports.

## Forbidden outputs

- Holdout tuning; averaged-away ACL/citation/deadline failures; missing raw samples; duplicate Combined keyword extraction; inferred managed proof.

## Ordered actions

1. Freeze candidate/data/configuration/methodology.
2. Score profiles, routes, Hybrid channels, codes/aliases, answers/citations/refusals/limits, tables, and Combined gain.
3. Measure BM25 tokenizer/Arabic parity/typed queries/75-survivor/300-scan/recheck/lag/outage/rebuild.
4. Measure all route first-evidence/token/completion/deadlines and every model/tool/token/cost call.
5. Measure graph mapping/survival/language coverage/current-version/latency/writer throughput/ETA/seven-day feasibility/cost.
6. Compare every value to signed targets.

## Acceptance checks

- **P09-03-A:** Zero ACL leaks; citation correctness ≥98%; completeness/faithfulness ≥90%; routing ≥90%; Hybrid Recall@10 ≥85%; exact Recall@5 ≥98%; alias Recall@10 ≥95%; Combined gain ≥10 points within cost/latency. Evidence: immutable report. Failure: requalify/no-go.
- **P09-03-B:** Route percentiles/deadlines and call/tool ceilings pass or limits are reduced/re-signed. Evidence: raw samples/ledger. Failure: sizing route.
- **P09-03-C:** BM25 exact numeric/query/recheck/lag/outage/rebuild gates pass. Evidence: BM25 report. Failure: blocker/envelope decision.
- **P09-03-D:** Graph mapping, per-language survival, concurrency-one throughput, ETA, cost, and seven-day maintenance are proven. Evidence: graph report. Failure: reduce graph envelope/quarantine.

## Negative tests

- Selective ACL filters, ParadeDB kill/version mismatch, insufficient/contradictory/media/negation/historical/summary cases, naive-union ablation, and budget/deadline exhaustion.

## Stop routes

- Stop on leakage, drift, missing samples, unbudgeted calls, ACL/citation failure, or unverifiable metrics.
- Use sizing ladder; leave pooling/real EC2/CDN/KMS/managed restore to Phase 10.

## Required evidence

Append P09-03 to `docs/development/phase-09-local-release-candidate-evidence.md`: identities/method, raw paths, per-language/class scores, percentiles/deadlines, call/token/cost ledger, BM25/graph reports, target comparison, repairs, and signed envelope decisions.
