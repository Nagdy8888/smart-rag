---
phase: 6
packet: 1
status: pending
title: "Implement authenticated, idempotent run admission with server-derived database authorization, deadlines, recursion/model/tool ceilings, durable reservations, read-access auditing, and authorized runtime context."
requirement_ids: [P06-01]
---

# Packet 1 — Implement authenticated, idempotent run admission with server-derived database authorization, deadlines, recursion/model/tool ceilings, durable reservations, read-access auditing, and authorized runtime context.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

## Preconditions

- Phases 1–5 and their accepted evidence provide the actual JWT/database authorization, role/RLS, durable budget/reservation/usage, idempotency/run, audit-chain, QueryProfile/Hybrid, and graph handoff contracts.
- Inspect real schemas, migrations, repository commands, pinned gateway/checkpointer APIs, signed [`QUALITY_TARGETS.md`](../../../../../docs/QUALITY_TARGETS.md), and governance decisions; plan text is not proof they exist.
- The authorized runtime context, rate/concurrency checks, and reservation operation can be exercised with real local database boundaries.

## Allowed outputs

- Admission services/nodes, typed authorized runtime context, idempotent run creation/reconnect, deadline/step/call/tool counters, durable reservation/usage/true-up wiring, restricted-read audit issuance, tests, and Phase 6 evidence.
- Additive migrations and API/service contracts strictly required for admission, unique idempotency, reservation, usage, heartbeat/expiry reconciliation, or append-only audit behavior.

## Forbidden outputs

- Client-derived authorization, process/Valkey-only authority, shared budget-row relocking per model call, duplicate paid work on retry, unbounded gateway/tool work, graph/BM25/cache output used as authorization, or direct runtime audit inserts.
- Implementing profiling/routing, fusion/answering, optional discovery, router breadth, SSE transport, retention reaping, UI, managed AWS anchors, or later-phase infrastructure.

## Ordered actions

1. Verify the Supabase JWT, reload current user/company/role/document scope, disabled/session-revoked state, and run/conversation ownership from authoritative database state; pass only this typed context into [`apps/agents/src/smart_rag_agents/query/`](../../../../../apps/agents/src/smart_rag_agents/query/).
2. Apply FastAPI-owned pre/post-auth rate and concurrency admission before cost, while preserving the provider-versus-application ownership in packet 5. Reject rather than reserve when current authorization or concurrency fails.
3. Enforce one client-generated message key with a database unique constraint on user/conversation/key. Atomically create one run or reconnect to the existing authorized run; retries never repeat paid work.
4. Assign the route envelope: deadlines of 25 seconds Hybrid, 45 Combined, 30 StructuredTable, 50 Composite, and 10 inspection; `recursion_limit=24`; at most one correction and three subquestions.
5. Set model ceilings of seven Hybrid, eight Combined, six StructuredTable, nine Composite, and three inspection calls; Hybrid normally uses at most six and uses call seven only for correction rerank or a due summary that cannot safely defer. Set at most four tool executions, five for Composite, one optional discovery round, one side-effecting tool, and three optional manifests.
6. In one short transaction, lock company/user budget rows once, reserve the route's maximum approved token/cost envelope in one `budget_reservations` row, and release shared rows. Rate limits remain separate from spend control.
7. Give each profiling, rewrite, LightRAG internal, rerank, answer, summary, and verifier call a hard cap. Atomically consume only the run-local reservation/optimistic version and write immutable `llm_usage`; never relock the shared company row per call.
8. On completion, sum actual usage and transactionally refund/true-up. Heartbeat, expiry, crash recovery, and the budget reconciler perform the same idempotent settlement without conflating packet 7's idempotency/event reaper.
9. Emit append-only audit events through the private chained insert interface for signed download issuance, restricted-document preview, and restricted evidence included in a completed run. Store actor, document-version, run, citation, and purpose identifiers without full passage text.
10. Test concurrent duplicate admission, revoked/disabled/role-changed users, reservation contention, timeout-after-provider-send, process death at each admission/usage/settlement boundary, cancellation, and retry/reconnect; append exact evidence.

## Acceptance checks

- Unauthorized, stale-role, revoked-session, cross-user run, deleted-conversation, and over-budget requests create no paid run and receive no authorized runtime context.
- Concurrent sends with the same user/conversation/key converge on one run, one reservation, and one paid execution; authorized retries reconnect.
- Every route enforces its exact deadline, recursion, correction, subquestion, model-call, tool, discovery, manifest, and side-effect ceilings and terminates safely on exhaustion.
- All gateway calls consume one durable run reservation, immutable usage matches provider attempts including timeout-after-send, completion/crash reconciliation cannot overspend, and no call hot-relocks shared budget rows.
- Restricted preview/download/evidence events are append-only, chained through the controlled function, content-minimized, and correlated to actor/version/run/citation/purpose.

## Negative tests

- Forged/stale JWT claims, ACL downgrade race, disabled user, foreign conversation/run/key, key collision with changed payload, duplicate concurrent request, reservation exhaustion, optimistic-version conflict, crash before/after provider response, double true-up, deadline/recursion/call/tool overrun, and direct audit insert/update/delete all fail safely.
- A cache hit, BM25 result, graph path, client route, client role, in-memory counter, or Valkey state cannot authorize, enlarge budget, or bypass canonical checks.

## Stop routes

- Stop if prerequisite authorization/budget/idempotency/audit schemas or signed ceilings are absent, a real local boundary cannot be tested, provider usage cannot be reconciled after ambiguous sends, or one-paid-run semantics require weakening authorization or durability.
- Any security, cost, deadline, or acceptance change requires an approved ADR/plan update; do not invent tables, defaults, or success evidence.

## Required evidence

- Append to [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md): inspected schema/API versions, authorization matrix, unique-key/concurrency traces, reservation and immutable usage ledgers, exact route ceilings, provider-attempt/crash/settlement results, restricted-read audit rows/hash-chain tests, commands/exit codes, deviations, rollback, and packet 2 handoff.
