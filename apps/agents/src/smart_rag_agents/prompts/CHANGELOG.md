---
title: Prompt changelog
owner: engineering-lead
status: draft
last-reviewed: 2026-08-16
audience: engineering
---

# Prompt changelog

Phase 6 Packet 3 adds the canonical answer and atomic-link verifier
prompts. Summary, optional-tool, and SSE prompts remain later packets.

| Version | Date | Change |
| --- | --- | --- |
| `query_profile_v1` | 2026-08-14 | Initial bounded profile extraction prompt. No retrieval or answer generation. |
| `rerank_v1` | 2026-08-14 | Structured top-20 rerank. No answer generation or tools. |
| `answer_v1` | 2026-08-16 | One grounded answer from canonical passages and deterministic table values. |
| `verifier_v1` | 2026-08-16 | One batched check of at most six atomic links. No second call. |

Related: [QUERY_PROFILE_EVAL.md](../../../../../docs/evaluation/QUERY_PROFILE_EVAL.md) ·
[COMBINED_FUSION.md](../../../../../docs/agent/COMBINED_FUSION.md) ·
[ANSWER_VERIFICATION.md](../../../../../docs/agent/ANSWER_VERIFICATION.md)

[docs index](../../../../../docs/README.md)
