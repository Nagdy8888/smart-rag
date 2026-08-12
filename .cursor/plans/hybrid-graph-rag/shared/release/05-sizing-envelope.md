---
name: hybrid-graph-rag-release-sizing-envelope
status: active
applies_to: phases-09-through-11
source_phases:
  - ../../09-phase-local-release-candidate.md
  - ../../10-phase-managed-staging.md
  - ../../11-phase-production.md
---

# Release sizing envelope

## Canonical targets

The [global contracts](../../00-global-contracts.md#provisional-measurable-targets-and-mandatory-sign-off) own the signed quality, capacity, latency, deadline, model-call, tool, throughput, graph-maintenance, cost, temporal, availability, migration-compatibility, and evaluation targets. This contract does not replace or relax them.

The starting capacity envelope is 10,000 Hybrid document versions, 1,000,000 canonical chunks, 25 concurrently active users, and five simultaneous query runs. The initial graph-eligible envelope is 2,000 current document versions and 200,000 graph source chunks. The combined steady-state vector working set must fit within 60% of selected database RAM with documented maintenance headroom. Availability is best-effort single-host v1 with RTO at most four hours and RPO at most 24 hours. The workload and availability trigger thresholds remain those in the global contract, including the 70% database or EC2 CPU/memory/IO trigger windows and the 80% supported-envelope utilization trigger.

## Phase 9 local sizing gate

Phase 9 measures the exact immutable local candidate images and production configuration profile through:

- corpus seeding through the approved envelope;
- Hybrid and Combined p95 plus route-specific first-evidence, first-token, completion, and hard-deadline behavior;
- StructuredTable and graph-inspection p95 and deadlines;
- ParadeDB BM25 top-75 p95, index size, RAM, write throughput, projection lag, clean rebuild duration, and foreground contention;
- LightRAG local, global, and graph-hybrid p95;
- Supabase CPU, IO, cache, pooled and direct pressure, connection caps, and per-role timeout behavior;
- measured and extrapolated HNSW steady/build memory for the pinned model and dimension, including LightRAG's separate vectors;
- reserve-once shared budget-row lock wait;
- five concurrent streams with event-loop lag and heartbeat jitter;
- graph-survival ratio and concurrency-one writer documents/hour, backlog ETA, onboarding duration, and cost;
- OCR memory;
- EC2-equivalent memory and CPU;
- both Valkey services' memory, OOM, ACL-denied, outage, and degraded modes;
- local egress enforcement; and
- local database plus Storage backup, restore, reconciliation, and derived BM25 rebuild time.

Exercise maintenance BM25 rebuild plus HNSW and graph work against foreground queries and the documented 70% pause or isolation triggers. Phase 9 also measures model calls and cost, cache behavior, CPU offload, graph-cleanup and seven-day rebuild feasibility, projection lag below five minutes during normal ingestion, and all route-specific global quality and latency ceilings.

Phase 9 evidence belongs in `docs/development/phase-09-local-release-candidate-evidence.md`. It records measured p50/p95 values, sample size and workload, hardware and Docker limits, image/configuration/data versions, confidence or run-to-run variance, raw artifact locations, and the signed envelope decision.

## Phase 10 managed extension

Phase 10 extends, and does not retroactively block or replace, the Phase 9 local gate with:

- managed Supabase session and transaction pooling behavior;
- any replica behavior, with mandatory primary ACL and current-version revalidation;
- actual managed database pressure and selected plan limits;
- real EC2 CPU, RAM, disk, EBS, Docker, ParadeDB, Valkey, OCR, API, worker, and offload resources;
- production-equivalent private ParadeDB index, projection, query, clean rebuild, and foreground-contention behavior;
- WAF and CloudFront behavior for the real 50-second stream under asserted 90-second read and keep-alive settings;
- provider egress controls and monitored denials;
- AWS KMS and S3 Object Lock audit anchors;
- managed database and Storage restore/reconciliation time;
- instance rebuild and derived BM25 rebuild/parity time;
- operational and billing alarm delivery; and
- the same route, deadline, connection, budget-lock, event-loop, heartbeat, graph-throughput, and maintenance isolation gates under production-equivalent topology.

Phase 10 uses only synthetic or redacted data. Its evidence belongs in `docs/development/phase-10-managed-staging-evidence.md` and must relate every managed result to the exact Phase 9 candidate image/configuration and signed target.

## Decision ladder before production

For every missed quality, latency, capacity, cost, restore, RTO/RPO, or contention target, record one explicit outcome:

1. repair and rerun the failed gate;
2. execute the approved workload-isolation ladder;
3. resize the managed Supabase, EC2, EBS, ParadeDB, Valkey, CPU/offload, or other relevant resource and rerun;
4. split or move ParadeDB only through an approved architecture/licensing decision and full staging requalification;
5. reduce the documented supported envelope, graph envelope, or advertised limit with client sign-off and rerun at the reduced value; or
6. stop release.

Do not average away ACL, grounding, deletion, budget, restore, rebuild, or deadline failures. Do not infer managed success from local EC2-equivalent measurements. Do not use a larger production tier than staging without proving that the change is a production-safe delta rather than an unqualified topology change.

The graph envelope may increase only when a full clean-workspace rebuild meets the seven-day maintenance SLO and approved maintenance budget. Before graph launch, the monthly maintenance reserve remains at least `max(USD 800, 4 × measured full-rebuild cost)`. If one rebuild cannot finish inside seven days or the reserve is unavailable, reduce the graph envelope or keep graph service quarantined while canonical deletion and Hybrid continue safely.

## Phase 11 promotion constraint

Phase 11 does not discover or expand capacity. It confirms that production plan, region, resource, timeout, budget, and alarm values are the exact qualified Phase 10 values or approved environment-specific values within the signed envelope.

Evidence belongs in `docs/development/phase-11-production-evidence.md`. Any larger scale claim, new resource topology, changed managed feature, reduced safety headroom, unqualified replica path, or changed engine/index configuration returns to Phase 10 for synthetic qualification and required approval before user access.

## Failure routes

- Missing or irreproducible measurements block the owning phase.
- A local miss is resolved, isolated/resized, or reduced and re-signed before Phase 10; managed blockers are handed off without requiring cloud proof in Phase 9.
- A managed miss blocks Phase 11 until corrected and requalified with synthetic/redacted staging data.
- A production drift or unsupported expansion stops promotion and returns to Phase 10.
