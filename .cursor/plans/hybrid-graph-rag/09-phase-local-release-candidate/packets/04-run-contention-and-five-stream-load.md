---
phase: 9
packet: 4
status: pending
title: "Run foreground-plus-maintenance Supabase/HNSW/ParadeDB/graph load, connection caps, budget-lock contention, CPU offload, and five-stream event-loop tests."
requirement_ids: [P09-04]
---

# Packet 4 — Run foreground-plus-maintenance Supabase/HNSW/ParadeDB/graph load, connection caps, budget-lock contention, CPU offload, and five-stream event-loop tests.

Required contracts: [phase shared](../00-shared-contracts.md), [local release gates](../../shared/release/01-local-release-gates.md), and [sizing envelope](../../shared/release/05-sizing-envelope.md).

## Preconditions

- P09-01–03 pass; load mixes, maintenance work, telemetry, limits, and 70% pause/isolation triggers are fixed.

## Allowed outputs

- Load/connection/CPU/memory/IO/cache/event-loop/heartbeat/lock reports; bounded tuning; signed resize/isolation/reduction decision.

## Forbidden outputs

- Unbounded/destructive/cloud load; hidden drops/deadline extensions; bypassed locks; local-as-managed claims.

## Ordered actions

1. Freeze workload, concurrency, hardware, Docker limits, pools, and telemetry.
2. Run foreground routes with BM25 rebuild, HNSW maintenance, and graph work.
3. Measure Supabase/ParadeDB connections, CPU/IO/cache/RAM/latency/lag and role timeouts.
4. Measure HNSW/LightRAG/graph/OCR/Valkey/host resource behavior.
5. Contend reserve-once budget row.
6. Run five Composite streams with bounded CPU offload, lag, jitter, disconnect, resume, and deadlines.

## Acceptance checks

- **P09-04-A:** Foreground gates hold during maintenance or 70% pause/isolation activates. Evidence: synchronized traces. Failure: isolate/resize/reduce.
- **P09-04-B:** Connection caps/timeouts prevent exhaustion. Evidence: pool report. Failure: blocker.
- **P09-04-C:** Budget lock meets wait gate without overspend/deadlock. Evidence: ledger/lock telemetry. Failure: stop.
- **P09-04-D:** Five streams meet event-loop, heartbeat, offload, and deadline gates. Evidence: timelines. Failure: repair/re-sign concurrency.
- **P09-04-E:** OCR/HNSW/graph/ParadeDB/Valkey/host resources stay bounded. Evidence: peak/steady report. Failure: sizing ladder.

## Negative tests

- Exceed 70% maintenance trigger, saturate pools, contend/cancel/crash budget reservations, force CPU work, and reach Valkey/container memory limits.

## Stop routes

- Stop on unbounded use, overspend, pool exhaustion, missed deadline without approved partial, lost heartbeat, unauthorized evidence, or missing telemetry.
- Hand managed pooling/real EC2/CDN extension to Phase 10.

## Required evidence

Append P09-04 to `docs/development/phase-09-local-release-candidate-evidence.md`: frozen profile, raw telemetry, percentiles/deadlines, pools/timeouts, 70% actions, lock waits, stream timelines, resource peaks, failures/repairs, and signed envelope.
