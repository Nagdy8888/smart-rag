---
title: Prompt changelog
owner: engineering-lead
status: draft
last-reviewed: 2026-08-14
audience: engineering
---

# Prompt changelog

Phase 4 Packet 5 adds the rerank prompt. Answer, verifier, summary, and
tool prompts remain forbidden.

| Version | Date | Change |
| --- | --- | --- |
| `query_profile_v1` | 2026-08-14 | Initial bounded profile extraction prompt. No retrieval or answer generation. |
| `rerank_v1` | 2026-08-14 | Structured top-20 rerank. No answer generation or tools. |

Related: [QUERY_PROFILE_EVAL.md](../../../../../docs/evaluation/QUERY_PROFILE_EVAL.md)

[docs index](../../../../../docs/README.md)
