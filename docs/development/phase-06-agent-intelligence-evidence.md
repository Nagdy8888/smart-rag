---
title: Phase 6 agent-intelligence evidence index
owner: engineering-lead
status: draft
last-reviewed: 2026-08-26
audience: engineering, reviewers
---

# Phase 6 agent-intelligence evidence

Packet evidence lives under [phase-06/](./phase-06/). Append new
cleanup or BR packet records to a new file in that directory and
link it here. Do not grow this index past one topic.

Canonical packet evidence for
[Phase 6](../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md).
Packet 1 created this file. Phase status remains `pending` until the wrapper
gate is proven and accepted. Packet 1 does not mark the phase complete.

Related: [QUERY_ADMISSION.md](../agent/QUERY_ADMISSION.md) ·
[phase-06-query-agent-cleanup-baseline.md](./phase-06-query-agent-cleanup-baseline.md) ·
[QUERY_BUDGETS.md](../agent/QUERY_BUDGETS.md) ·
[QUERY_ROUTING.md](../agent/QUERY_ROUTING.md) ·
[COMBINED_FUSION.md](../agent/COMBINED_FUSION.md) ·
[ANSWER_VERIFICATION.md](../agent/ANSWER_VERIFICATION.md) ·
[OPTIONAL_TOOLS.md](../agent/OPTIONAL_TOOLS.md) ·
[SSE.md](../api/SSE.md) ·
[STREAMING_TIMEOUTS.md](../deployment/STREAMING_TIMEOUTS.md) ·
[QUALITY_TARGETS.md](../QUALITY_TARGETS.md) ·
[AUDIT_CHAIN.md](../security/AUDIT_CHAIN.md) ·
[docs index](../README.md)

| Packet / section | File | Lines |
| --- | --- | ---: |
| Prerequisites | [phase-06/prerequisites.md](./phase-06/prerequisites.md) | 11 |
| Packet 1 — authenticated idempotent run admission | [phase-06/packet-1-authenticated-idempotent-run-admission.md](./phase-06/packet-1-authenticated-idempotent-run-admission.md) | 193 |
| Packet 2 — memory, rewrite, profiling, route matrix, one correction | [phase-06/packet-2-memory-rewrite-profiling-route-matrix-one-correction.md](./phase-06/packet-2-memory-rewrite-profiling-route-matrix-one-correction.md) | 230 |
| Packet 3 — Combined fusion, table composition, answer, verifier | [phase-06/packet-3-combined-fusion-table-composition-answer-verifier.md](./phase-06/packet-3-combined-fusion-table-composition-answer-verifier.md) | 162 |
| Packet 4 — optional-tool registry and progressive disclosure | [phase-06/packet-4-optional-tool-registry-and-progressive-disclosure.md](./phase-06/packet-4-optional-tool-registry-and-progressive-disclosure.md) | 195 |
| Packet 5 — FastAPI security, rate ownership, cache, offload, isolation | [phase-06/packet-5-fastapi-security-rate-ownership-cache-offload-isolation.md](./phase-06/packet-5-fastapi-security-rate-ownership-cache-offload-isolation.md) | 181 |
| Packet 6 — versioned additive SSE, handshake, resume, heartbeats | [phase-06/packet-6-versioned-additive-sse-handshake-resume-heartbeats.md](./phase-06/packet-6-versioned-additive-sse-handshake-resume-heartbeats.md) | 170 |
| Packet 7 — checkpoints, store, reaper, governance, deletion | [phase-06/packet-7-checkpoints-store-reaper-governance-deletion.md](./phase-06/packet-7-checkpoints-store-reaper-governance-deletion.md) | 190 |
| Packet 8 — thin authenticated developer UI | [phase-06/packet-8-thin-authenticated-developer-ui.md](./phase-06/packet-8-thin-authenticated-developer-ui.md) | 134 |
| Packet 8 residual close-out (2026-08-16) | [phase-06/packet-8-residual-close-out-2026-08-16.md](./phase-06/packet-8-residual-close-out-2026-08-16.md) | 69 |
| P08-09 co-owned amendment — durable input and verified-final SSE | [phase-06/p08-09-co-owned-amendment-durable-input-and-verified-final-sse.md](./phase-06/p08-09-co-owned-amendment-durable-input-and-verified-final-sse.md) | 30 |
| P06-08 narrow fix — LangSmith Studio Chat compatibility (2026-08-25) | [phase-06/p06-08-narrow-fix-langsmith-studio-chat-compatibility-2026-08-25.md](./phase-06/p06-08-narrow-fix-langsmith-studio-chat-compatibility-2026-08-25.md) | 46 |
| P06-09 — Canonical general-chat amendment (2026-08-25) | [phase-06/p06-09-canonical-general-chat-amendment-2026-08-25.md](./phase-06/p06-09-canonical-general-chat-amendment-2026-08-25.md) | 49 |
| P06-10 — Typed knowledge-scope routing (2026-08-25) | [phase-06/p06-10-typed-knowledge-scope-routing-2026-08-25.md](./phase-06/p06-10-typed-knowledge-scope-routing-2026-08-25.md) | 49 |
| P06-11 — SSE stream lifecycle and LangSmith tracing (2026-08-25) | [phase-06/p06-11-sse-stream-lifecycle-and-langsmith-tracing-2026-08-25.md](./phase-06/p06-11-sse-stream-lifecycle-and-langsmith-tracing-2026-08-25.md) | 47 |
| P06-12 — General and user-text execution (2026-08-25) | [phase-06/p06-12-general-and-user-text-execution-2026-08-25.md](./phase-06/p06-12-general-and-user-text-execution-2026-08-25.md) | 146 |
| P06-13 — Authenticated `query_studio_live` (2026-08-25) | [phase-06/p06-13-authenticated-query-studio-live-2026-08-25.md](./phase-06/p06-13-authenticated-query-studio-live-2026-08-25.md) | 54 |
| P06-14 — Main chat origin UX (2026-08-25) | [phase-06/p06-14-main-chat-origin-ux-2026-08-25.md](./phase-06/p06-14-main-chat-origin-ux-2026-08-25.md) | 52 |
| P06-15 — Integrated verification (2026-08-25) | [phase-06/p06-15-integrated-verification-2026-08-25.md](./phase-06/p06-15-integrated-verification-2026-08-25.md) | 100 |
| LangSmith hosted online evaluators (2026-08-26) | [phase-06/langsmith-hosted-online-evaluators-2026-08-26.md](./phase-06/langsmith-hosted-online-evaluators-2026-08-26.md) | 105 |
| BR-1A — Brain-repair governance amendment (2026-08-26, pending acceptance) | [phase-06/br-1a-brain-repair-governance-amendment-2026-08-26-pending-acceptance.md](./phase-06/br-1a-brain-repair-governance-amendment-2026-08-26-pending-acceptance.md) | 65 |
| BR-2 — Profile classification gateway and runtime binding (2026-08-26, pending acceptance) | [phase-06/br-2-profile-classification-gateway-and-runtime-binding-2026-08-26-pending-accep.md](./phase-06/br-2-profile-classification-gateway-and-runtime-binding-2026-08-26-pending-accep.md) | 112 |
| BR-3 — Direct answer and graceful-degradation behavior (2026-08-26, accepted) | [phase-06/br-3-direct-answer-and-graceful-degradation-behavior-2026-08-26-accepted.md](./phase-06/br-3-direct-answer-and-graceful-degradation-behavior-2026-08-26-accepted.md) | 49 |
| Cleanup packet 1 — Governance, inventory, and baseline (2026-08-26) | [phase-06/cleanup-packet-1-governance-inventory-and-baseline-2026-08-26.md](./phase-06/cleanup-packet-1-governance-inventory-and-baseline-2026-08-26.md) | 44 |
| Cleanup packet 2 — Explicit scope nodes and agent node split (2026-08-26) | [phase-06/cleanup-packet-2-explicit-scope-nodes-and-agent-node-split-2026-08-26.md](./phase-06/cleanup-packet-2-explicit-scope-nodes-and-agent-node-split-2026-08-26.md) | 53 |
| Cleanup packet 3 — Core routing cleanup (2026-08-26) | [phase-06/cleanup-packet-3-core-routing-cleanup-2026-08-26.md](./phase-06/cleanup-packet-3-core-routing-cleanup-2026-08-26.md) | 52 |
| Cleanup packet 4 — Gateway and answer cleanup (2026-08-26) | [phase-06/cleanup-packet-4-gateway-and-answer-cleanup-2026-08-26.md](./phase-06/cleanup-packet-4-gateway-and-answer-cleanup-2026-08-26.md) | 58 |
| Cleanup packet 5 — Runtime, Studio, and persistence (2026-08-26) | [phase-06/cleanup-packet-5-runtime-studio-and-persistence-2026-08-26.md](./phase-06/cleanup-packet-5-runtime-studio-and-persistence-2026-08-26.md) | 63 |
| Cleanup packet 6 — Backend SSE split (2026-08-26) | [phase-06/cleanup-packet-6-backend-sse-split-2026-08-26.md](./phase-06/cleanup-packet-6-backend-sse-split-2026-08-26.md) | 56 |
| Cleanup packet 7 — Admission and Hybrid split (2026-08-26) | [phase-06/cleanup-packet-7-admission-and-hybrid-split-2026-08-26.md](./phase-06/cleanup-packet-7-admission-and-hybrid-split-2026-08-26.md) | 72 |
| Cleanup packet 8 — Query tracing and evaluation (2026-08-26) | [phase-06/cleanup-packet-8-query-tracing-and-evaluation-2026-08-26.md](./phase-06/cleanup-packet-8-query-tracing-and-evaluation-2026-08-26.md) | 58 |
| Cleanup packet 9 — Tests, docs, and dead-code closure (2026-08-26) | [phase-06/cleanup-packet-9-tests-docs-dead-code-2026-08-26.md](./phase-06/cleanup-packet-9-tests-docs-dead-code-2026-08-26.md) | 52 |
| Cleanup final-gates — Architecture, work counts, and repository gates (2026-08-26) | [phase-06/cleanup-final-gates-2026-08-26.md](./phase-06/cleanup-final-gates-2026-08-26.md) | 88 |
| P06-16 — Custom SSE progress and paced-reveal contract (2026-08-26) | [phase-06/p06-16-sse-custom-progress-amendment-2026-08-26.md](./phase-06/p06-16-sse-custom-progress-amendment-2026-08-26.md) | 32 |
| Overlay PDF Hybrid P13/P15/P16 (2026-09-09, blocked live gates) | [phase-06/overlay-pdf-hybrid-packets.md](./phase-06/overlay-pdf-hybrid-packets.md) | 86 |
