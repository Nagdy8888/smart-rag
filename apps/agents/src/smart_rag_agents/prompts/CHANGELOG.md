---
title: Prompt changelog
owner: engineering-lead
status: draft
last-reviewed: 2026-09-15
audience: engineering
---

# Prompt changelog

Phase 6 Packet 4 adds the Level 0 optional-catalog disclosure prompt.
Runtime v1 uses deterministic mapping; discovery is not retained.

| Version | Date | Change |
| --- | --- | --- |
| `query_profile_v1` | 2026-08-14 | Initial bounded profile extraction prompt. No retrieval or answer generation. |
| `query_profile_v1` | 2026-08-25 | Additive ``knowledge_scope`` / confidence fields. No second model call. |
| `query_profile_v1` | 2026-09-15 | Additive ``web`` knowledge-scope enum. Deterministic company/privacy guards still override. |
| `web_critique_v1` | 2026-09-15 | At most two follow-up public-web queries. No company retrieval. |
| `web_answer_v1` | 2026-09-15 | One Web answer from persisted excerpts. Cite only `web_source_id`. |
| `rerank_v1` | 2026-08-14 | Structured top-20 rerank. No answer generation or tools. |
| `answer_v1` | 2026-08-16 | One grounded answer from canonical passages and deterministic table values. |
| `answer_v2` | 2026-09-15 | Paragraph-mapped company answers with exact 1–1000 character spans. Provider omits `answer_text`. |
| `verifier_v1` | 2026-08-16 | One batched check of at most six atomic links. No second call. |
| `optional_catalog_v1` | 2026-08-16 | Level 0 catalog capabilities and immutable safety rules. No core retrieve tools. |
| `summary_v1` | 2026-08-16 | Compact conversation summary for LangGraph store. Preferences only; no source copies. Counted as `usage_kind=summary`. |
| `eval_judge_v1` | 2026-08-20 | One bounded synthetic agent-eval judge call. No retrieval, tools, retry, or holdout/private content. |
| `eval_pdf_judge_v1` | 2026-09-09 | Separate real-PDF judge. Does not reuse `eval_judge_v1`. |
| `conversation_title_v1` | 2026-08-26 | One-line session-rail title. No retrieval, tools, retry, or holdout/private content. |

Related: [QUERY_PROFILE_EVAL.md](../../../../../docs/evaluation/QUERY_PROFILE_EVAL.md) ·
[COMBINED_FUSION.md](../../../../../docs/agent/COMBINED_FUSION.md) ·
[ANSWER_VERIFICATION.md](../../../../../docs/agent/ANSWER_VERIFICATION.md) ·
[OPTIONAL_TOOLS.md](../../../../../docs/agent/OPTIONAL_TOOLS.md) ·
[MEMORY_DELETION.md](../../../../../docs/agent/MEMORY_DELETION.md)

[docs index](../../../../../docs/README.md)
