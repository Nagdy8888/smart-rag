---
title: Prompt changelog
owner: engineering-lead
status: draft
last-reviewed: 2026-10-13
audience: engineering
---

# Prompt changelog

- 2026-10-28: `web_answer_v2` preserves original language and question requirements and emits validated citation markers. `web_verifier_v1` checks whole-answer support, coverage, language and references in one counted call. Previous prompt files remain immutable.

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
| `rerank_v2` | 2026-09-24 | Pool-order labels `c01`-`c20` instead of chunk IDs; ordered label array plus per-label support; no echoed hash. Server appends unranked labels in fused order. `rerank_v1` stays immutable. |
| `answer_v1` | 2026-08-16 | One grounded answer from canonical passages and deterministic table values. |
| `answer_v2` | 2026-09-15 | Paragraph-mapped company answers with exact 1–1000 character spans. Provider omits `answer_text`. Chat scores leaves and PDF toolbar pages, never printed `page_label`. |
| `answer_v3` | 2026-09-16 | Surviving atomic-link claims only. Acronym expansions must be spelled in a supplied source. `answer_v2` stays immutable. |
| `answer_v4` | 2026-09-24 | Ordered claims with `source_id` + `span` citations; application assigns link IDs, paragraphs, and ownership. First claim answers directly. `answer_v3` stays immutable. |
| `answer_v4` | 2026-09-29 | Prefer expose Manual/Assist/Auto over figure Manual/Ask/Agent; prefer ADAS dated model defaults over undated gpt-4o@0 samples. Schema unchanged. |
| `answer_v4` | 2026-09-29 | Prefer exact heading/method/description-string/`window_size` literals over paraphrases. Schema unchanged. |
| `answer_v5` | 2026-10-02 | When asked, emit fenced Python code or GFM pipe tables in the first claim; soften one-sentence rule for those asks. Citation `span` stays exact source text. `answer_v4` stays immutable. |
| `answer_v6` | 2026-10-06 | Remove question-specific bullets (mode labels, named-example model defaults, chunking literals) and source-derived examples; generic rules only. Schema unchanged. `answer_v5` stays immutable. |
| `verifier_v1` | 2026-08-16 | One batched check of at most six atomic links. No second call. |
| `verifier_v2` | 2026-09-16 | Reject invented acronym expansions and fact literals missing from cited sources. One call, six-link cap unchanged. |
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
