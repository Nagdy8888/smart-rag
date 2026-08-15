---
name: implement-query-agent
description: Implements LangGraph query profiling, deterministic routing, Hybrid and LightRAG composition, progressive tool disclosure, grounding, verification, budgets, and SSE. Use for agent orchestration, tools, answers, citations, or streaming.
---

# Implement the Query Agent

Read the Phase 6 wrapper, `00-shared-contracts.md`, exactly one linked active packet, and only that packet's named shared contracts. Define typed state and node contracts before graph wiring; do not load sibling packets or infer behavior from legacy section numbers.

## Required execution order

1. Authenticate, authorize conversation scope, enforce endpoint-specific degraded rate limits/idempotency, and reserve the route-maximum durable budget once.
2. Load bounded recent messages plus persisted summary; treat all retrieved content as untrusted data.
3. Build a typed `QueryProfile` and preserve original/rewrite/decomposition audit fields; when a model is needed for both rewrite and profiling, use one structured preparation call.
4. Compile the complete deterministic `RetrievalPlan` matrix.
5. Bind core Hybrid, LightRAG, StructuredTable, and citation tools directly.
6. Use progressive discovery only for optional capabilities after role/feature filtering: one discovery/model round and at most three optional manifests per run.
7. Execute route branches concurrently only when independent and within deadline/model/tool budgets.
8. Resolve all candidates to authorized canonical evidence or deterministic table provenance.
9. Apply the exact Combined fusion algorithm and context budget.
10. Generate an answer using evidence IDs, then run deterministic citation/link checks.
11. For Combined inference, verify at most six atomic links in one batched model call.
12. Persist run/evidence/usage/audit records, true-up the run-local reservation, and stream sequenced events.

## Hard invariants

- Hybrid remains the base evidence path for factual answers.
- Graph prose is never answer evidence.
- Every relationship chain cites every link; unsupported links are omitted or explicitly refused.
- Global graph output steers Hybrid only.
- Combined with `graph_survival_ratio < 0.50` becomes effective Hybrid with `graph_survival_below_threshold`; `NoRetrieval` cannot make company-knowledge claims.
- One shared correction maximum: coverage below the frozen allow-listed query-class threshold (provisional `0.65`) without relationship signals may retry the same route; Hybrid below that threshold with a retained relationship/multi-hop signal may instead escalate to Combined. Never do both.
- Enforce hard deadlines: Hybrid 25s (full run, including answer), Combined 45s, StructuredTable 30s, Composite 50s, inspection 10s. Hybrid retrieval+rerank uses the Phase 4 retrieval slice inside that 25s envelope.
- Count every gateway model call, including one batched query-embedding call per retrieve: maxima are 7/8/6/9/3 for Hybrid/Combined/StructuredTable/Composite/inspection. Hybrid targets six; call seven is correction/second-rerank or non-deferrable summary headroom only. Tool calls are at most four, or five for Composite; use at most three subquestions and `recursion_limit=24`.
- Cancellation stops child work and reconciles reservations.
- Gateway calls atomically consume only the run-local reservation; shared company/user rows are not relocked per call. Reservations heartbeat during work and completion/crash/orphan reconciliation true-ups actual usage.
- Instrument event-loop lag/node CPU. Keep a pure-Python stage in-process only below the plan's p95 CPU threshold; otherwise use bounded process offload with cancellation and prove heartbeat jitter under five Composite runs.
- A graph/reranker/verifier failure degrades as documented; it never fabricates success.
- LangGraph checkpoints store compact state and the store holds summaries/preferences—not source documents. Deleted source citations become unavailable without rewriting historical conversations.

## Streaming proof

Test idempotent replay, sequence ordering, 15-second heartbeat, disconnect/reconnect, cancellation, duplicate submission, deadline partial result, exactly one terminal event, and the 50-second stream through staging CloudFront's explicit 90-second origin timeouts.

Use a fixture with at least 20 optional tools to prove unselected schemas never enter prompts and discovery improves selection enough to justify latency/tokens; otherwise replace it with deterministic mapping.
