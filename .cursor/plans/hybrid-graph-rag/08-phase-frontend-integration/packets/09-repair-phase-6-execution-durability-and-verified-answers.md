---
phase: 8
packet: 9
status: complete
title: "Repair Phase 6 execution durability and verified answer delivery"
requirement_ids: [P08-09]
---

# Packet 9 — Repair Phase 6 execution durability and verified answer delivery

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-08 readiness/DSN repair is in place. Phase 6 admission-budget and SSE resume tests exist.

## Allowed outputs

Durable admission input, verified-final SSE mapping, one terminal, settlement, Phase 6 and Phase 8 evidence updates.

## Forbidden outputs

Fake token streaming, emitting unverified draft answer_text, redesigning routing/prompts/retrieval, unchecking completed Phase 6 packets.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-09 — Repair Phase 6 execution durability and verified answer delivery

Purpose: repair the Phase 6-owned production executor contract so admitted runs survive process changes, deliver a non-empty verified final answer, terminate exactly once, and settle budgets.

Ownership: this is a co-owned Phase 6/Phase 8 defect amendment. It must preserve the completed Phase 6 admission-budget and SSE resume contracts, update both phase evidence records, and remain green against their test suites.

Primary files:

- [`apps/backend/src/smart_rag_api/services/sse_stream.py`](apps/backend/src/smart_rag_api/services/sse_stream.py)
- [`apps/backend/src/smart_rag_api/routers/conversations.py`](apps/backend/src/smart_rag_api/routers/conversations.py)
- [`apps/agents/src/smart_rag_agents/query/nodes/pipeline.py`](apps/agents/src/smart_rag_agents/query/nodes/pipeline.py), the compiled query graph, and their contract tests only if needed to expose/verify the existing typed final state; no routing/prompt/retrieval redesign.
- existing query admission/run/message services under `packages/core` and `apps/backend`
- existing `app.messages`, `app.runs`, `app.query_run_events`, and reservation migrations/functions; add a migration only if the existing durable schema cannot meet the contract.
- production-executor unit/contract/integration tests and Phase 6/Phase 8 evidence.

Implementation:

- Persist the admitted user message in existing `app.messages` before returning a successful 202. Process memory may cache execution handles but must not be the only copy of paid input.
- If durable message persistence fails after reservation, mark the run terminal and release/settle the reservation; do not return fake admission.
- On resume/restart, reconstruct the authorized run input from durable run/conversation/message records. Never trust a browser-supplied replacement message for an existing run.
- Consume LangGraph `stream_mode="updates"` as node-keyed envelopes. Add a pinned contract test using the real compiled runtime shape; do not flatten or guess fields.
- For every node update, emit only allow-listed typed SSE fields. Status events use the node name and typed status. Limitations use signed codes only.
- Do not emit the answer node’s draft `answer_text`. Hold the typed candidate until the actual verification node completes, then validate the final state as `AnswerPayload`; derive the node name and envelope path from the pinned real-runtime test instead of assuming `answer.answer_text`.
- Emit the final verified/refused/partial `answer_text` as one or more non-empty persisted `token_delta` compatibility events, each at most the catalog’s 4096-character bound, with no artificial delay. Never emit unverified prose, raw retrieved passages, tracebacks, secrets, or duplicate text.
- Superseded in part by P08-24 / P06-16 / ADR-verified-answer-paced-reveal: backend emission and persistence remain immediate and verified-final; production streaming may add `custom` v2 after the pinned contract test; frontend presentation pacing must not delay this packet’s terminal, settlement, or resume contracts. This completed packet is not unchecked.
- Persist each SSE event before flushing. Reconnect replays stored events by sequence and never restarts the graph or charges again.
- Persist the final verified/refused/partial assistant answer to the existing conversation message store when allowed by the canonical memory policy.
- Emit `completed` only after a non-empty answer/refusal payload has been emitted and all required final writes succeed. A successful graph with no answer becomes a safe typed `error`, never “Answer ready.”
- Map typed partial/refusal/deadline states to `partial` or the approved limitation sequence; do not convert them to generic completion.
- Ensure exactly one of `completed`, `partial`, `cancelled`, or `error` is durable per run.
- On every terminal path, call the existing reservation true-up/release service exactly once with recorded usage. Failed/cancelled runs must not remain indefinitely `reserved`.
- Include `run_id` in structured server logs while retaining sanitized client error codes. Never log user message or source content.

Acceptance tests:

- Real production executor with a deterministic bound gateway emits `schema`, status events, at least one non-empty `token_delta`, optional usage/citations, then exactly one terminal.
- A real compiled-graph test proves node-keyed updates are interpreted correctly and that no answer text is emitted before verification; a flat fake update test is insufficient.
- `completed` with zero answer text is impossible.
- Error, cancellation, refusal, deadline, and partial paths each settle the reservation exactly once.
- Disconnect after sequence N and resume yields no duplicated text, no duplicate provider call, monotonic sequence, and one terminal.
- API restart after admission can recover durable input and finish, or fail terminally and settle; no run remains orphaned pending.
- Foreign/unauthorized run replay remains 404 and reveals no existence detail.
- Existing Phase 6 admission, budget consume/true-up, deadline, cancellation, ownership, idempotency, one-terminal, and replay/resume suites pass unchanged or with an explicitly documented compatible assertion update.

## Acceptance checks

Production executor emits schema, status, at least one non-empty token_delta after verification, then exactly one terminal. Reservations settle once. Phase 6 suites remain green.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if the real compiled graph envelope cannot be pinned by a contract test. Do not invent node names.

## Required evidence

Append `P08-09` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
