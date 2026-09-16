---
title: Phase 6 agent-intelligence evidence index
owner: engineering-lead
status: draft
last-reviewed: 2026-09-16
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
| P06-09 — Canonical general-chat amendment (2026-08-25; accepted 2026-09-10) | [phase-06/p06-09-canonical-general-chat-amendment-2026-08-25.md](./phase-06/p06-09-canonical-general-chat-amendment-2026-08-25.md) | 49 |
| P06-19 — Local PDF evaluation overlay (2026-09-10) | [phase-06/p06-19-local-pdf-evaluation-overlay-2026-09-10.md](./phase-06/p06-19-local-pdf-evaluation-overlay-2026-09-10.md) | 47 |
| P06-20 — PDF eval workspace store (2026-09-10) | [phase-06/p06-20-pdf-eval-workspace-store-2026-09-10.md](./phase-06/p06-20-pdf-eval-workspace-store-2026-09-10.md) | 40 |
| P06-21 — PDF eval workspace API (2026-09-10) | [phase-06/p06-21-pdf-eval-workspace-api-2026-09-10.md](./phase-06/p06-21-pdf-eval-workspace-api-2026-09-10.md) | 40 |
| P06-22 — PDF eval workspace UI (2026-09-10) | [phase-06/p06-22-pdf-eval-workspace-ui-2026-09-10.md](./phase-06/p06-22-pdf-eval-workspace-ui-2026-09-10.md) | 41 |
| P06-23 — PDF heading extraction (2026-09-10) | [phase-06/p06-23-pdf-heading-extraction-2026-09-10.md](./phase-06/p06-23-pdf-heading-extraction-2026-09-10.md) | 60 |
| P06-24 — PDF eval channel diagnostics (2026-09-10) | [phase-06/p06-24-pdf-eval-channel-diagnostics-2026-09-10.md](./phase-06/p06-24-pdf-eval-channel-diagnostics-2026-09-10.md) | 38 |
| P06-25 — PDF eval retrieval repair (2026-09-10) | [phase-06/p06-25-pdf-eval-retrieval-repair-2026-09-10.md](./phase-06/p06-25-pdf-eval-retrieval-repair-2026-09-10.md) | 37 |
| P06-26 — Retrieval cache and holdout gates (2026-09-10) | [phase-06/p06-26-retrieval-cache-and-holdout-gates-2026-09-10.md](./phase-06/p06-26-retrieval-cache-and-holdout-gates-2026-09-10.md) | 41 |
| P06-27 — Hosted webapp evaluation amendment (2026-09-10) | [phase-06/p06-27-hosted-webapp-evaluation-amendment-2026-09-10.md](./phase-06/p06-27-hosted-webapp-evaluation-amendment-2026-09-10.md) | 90 |
| P06-28 — Hosted quiz-case schema and app_api RPCs (2026-09-10) | [phase-06/p06-28-eval-quiz-case-database-2026-09-10.md](./phase-06/p06-28-eval-quiz-case-database-2026-09-10.md) | 108 |
| P06-29 — DB-backed pdf-eval case API (2026-09-10) | [phase-06/p06-29-eval-quiz-case-api-2026-09-10.md](./phase-06/p06-29-eval-quiz-case-api-2026-09-10.md) | 108 |
| P06-30 — Durable exam-run schema and hidden conversations (2026-09-10) | [phase-06/p06-30-eval-exam-database-2026-09-10.md](./phase-06/p06-30-eval-exam-database-2026-09-10.md) | 114 |
| P06-31 — Restart-safe production-corpus Hybrid exam runner (2026-09-13) | [phase-06/p06-31-eval-exam-runner-2026-09-13.md](./phase-06/p06-31-eval-exam-runner-2026-09-13.md) | 96 |
| P06-32 — Exam start, poll, cancel, latest report APIs (2026-09-13) | [phase-06/p06-32-eval-exam-api-2026-09-13.md](./phase-06/p06-32-eval-exam-api-2026-09-13.md) | 93 |
| P06-33 — Ask Save to quiz beside thumbs (2026-09-13) | [phase-06/p06-33-ask-quiz-capture-2026-09-13.md](./phase-06/p06-33-ask-quiz-capture-2026-09-13.md) | 80 |
| P06-34 — Admin case review, gold picker, stale repair (2026-09-13) | [phase-06/p06-34-admin-eval-curation-2026-09-13.md](./phase-06/p06-34-admin-eval-curation-2026-09-13.md) | 87 |
| P06-35 — Admin Recall@10 scoreboard, exam progress (2026-09-13) | [phase-06/p06-35-admin-exam-board-2026-09-13.md](./phase-06/p06-35-admin-exam-board-2026-09-13.md) | 91 |
| P06-36 — Hosted evaluation workspace close (2026-09-13) | [phase-06/p06-36-hosted-eval-verification-2026-09-13.md](./phase-06/p06-36-hosted-eval-verification-2026-09-13.md) | 115 |
| P06-37 — Advanced web research overlay (2026-09-14) | [phase-06/p06-37-advanced-web-research-amendment-2026-09-14.md](./phase-06/p06-37-advanced-web-research-amendment-2026-09-14.md) | 90 |
| P06-38 — Bounded Exa REST gateway (2026-09-14) | [phase-06/p06-38-exa-rest-gateway-2026-09-14.md](./phase-06/p06-38-exa-rest-gateway-2026-09-14.md) | 70 |
| P06-39 — Run-scoped web evidence store (2026-09-15) | [phase-06/p06-39-web-evidence-store-2026-09-15.md](./phase-06/p06-39-web-evidence-store-2026-09-15.md) | 106 |
| P06-40 — Four-mode admission and Web envelope (2026-09-15) | [phase-06/p06-40-four-mode-routing-2026-09-15.md](./phase-06/p06-40-four-mode-routing-2026-09-15.md) | 141 |
| P06-41 — Bounded iterative Web research graph (2026-09-15) | [phase-06/p06-41-web-research-graph-2026-09-15.md](./phase-06/p06-41-web-research-graph-2026-09-15.md) | 124 |
| P06-42 — Four-mode Ask dropdown UX (2026-09-15) | [phase-06/p06-42-four-mode-ask-ux-2026-09-15.md](./phase-06/p06-42-four-mode-ask-ux-2026-09-15.md) | 98 |
| P06-43 — Integrated Web gates (2026-09-15) | [phase-06/p06-43-web-research-gates-2026-09-15.md](./phase-06/p06-43-web-research-gates-2026-09-15.md) | 68 |
| P06-44 — PDF paragraph-citation overlay (2026-09-15) | [phase-06/p06-44-pdf-paragraph-citations-amendment-2026-09-15.md](./phase-06/p06-44-pdf-paragraph-citations-amendment-2026-09-15.md) | 93 |
| P06-45 — Paragraph mappings and fail-closed verification (2026-09-15) | [phase-06/p06-45-pdf-paragraph-grounding-2026-09-15.md](./phase-06/p06-45-pdf-paragraph-grounding-2026-09-15.md) | 110 |
| P06-46 — ACL-safe PDF citation persistence (2026-09-15) | [phase-06/p06-46-pdf-citation-persistence-2026-09-15.md](./phase-06/p06-46-pdf-citation-persistence-2026-09-15.md) | 108 |
| P06-47 — Inline PDF paragraph citation UI (2026-09-15) | [phase-06/p06-47-inline-pdf-citation-ui-2026-09-15.md](./phase-06/p06-47-inline-pdf-citation-ui-2026-09-15.md) | 88 |
| P06-48 — PDF citation accuracy gates (2026-09-15) | [phase-06/p06-48-pdf-citation-gates-2026-09-15.md](./phase-06/p06-48-pdf-citation-gates-2026-09-15.md) | 129 |
| P06-49 — Live RAG failure remediation overlay (2026-09-16) | [phase-06/p06-49-live-rag-failure-remediation-amendment-2026-09-16.md](./phase-06/p06-49-live-rag-failure-remediation-amendment-2026-09-16.md) | 93 |

| P06-10 — Typed knowledge-scope routing (accepted 2026-09-10) | [phase-06/p06-10-typed-knowledge-scope-routing-2026-08-25.md](./phase-06/p06-10-typed-knowledge-scope-routing-2026-08-25.md) | 73 |
| P06-11 — SSE stream lifecycle and LangSmith tracing (closed 2026-09-13) | [phase-06/p06-11-sse-stream-lifecycle-and-langsmith-tracing-2026-08-25.md](./phase-06/p06-11-sse-stream-lifecycle-and-langsmith-tracing-2026-08-25.md) | 80 |
| P06-12 — General and user-text execution (closed 2026-09-13) | [phase-06/p06-12-general-and-user-text-execution-2026-08-25.md](./phase-06/p06-12-general-and-user-text-execution-2026-08-25.md) | 165 |
| P06-13 — Authenticated `query_studio_live` (closed 2026-09-13) | [phase-06/p06-13-authenticated-query-studio-live-2026-08-25.md](./phase-06/p06-13-authenticated-query-studio-live-2026-08-25.md) | 70 |
| P06-14 — Main chat origin UX (closed 2026-09-13) | [phase-06/p06-14-main-chat-origin-ux-2026-08-25.md](./phase-06/p06-14-main-chat-origin-ux-2026-08-25.md) | 75 |
| P06-15 — Integrated verification (closed 2026-09-13) | [phase-06/p06-15-integrated-verification-2026-08-25.md](./phase-06/p06-15-integrated-verification-2026-08-25.md) | 145 |
| P06-16 — Custom SSE progress and paced-reveal contract (closed 2026-09-13) | [phase-06/p06-16-sse-custom-progress-amendment-2026-08-26.md](./phase-06/p06-16-sse-custom-progress-amendment-2026-08-26.md) | 42 |
| P06-17 — PDF Hybrid agent evaluation (live qualification blocked) | [phase-06/p06-17-pdf-agent-evaluation-2026-09-13.md](./phase-06/p06-17-pdf-agent-evaluation-2026-09-13.md) | 57 |
| P06-18 — Private-PDF holdout (blocked; not opened) | [phase-06/p06-18-pdf-holdout-blocked-2026-09-13.md](./phase-06/p06-18-pdf-holdout-blocked-2026-09-13.md) | 22 |
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
| Overlay PDF Hybrid P13/P15/P16 (2026-09-09, blocked live gates) | [phase-06/overlay-pdf-hybrid-packets.md](./phase-06/overlay-pdf-hybrid-packets.md) | 86 |
