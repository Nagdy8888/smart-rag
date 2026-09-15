---
title: Query budget engineering defaults
owner: engineering-lead
status: draft
last-reviewed: 2026-09-15
audience: engineering
phase_packet: Phase 6 Packet 1
---

# Query budget engineering defaults

There is no signed per-call USD table. Values below are Phase 6 engineering
defaults derived from `QT-COST-001` (USD 200/month) and the signed call
ceilings in [QUALITY_TARGETS.md](../QUALITY_TARGETS.md). They do not replace
those signed rows. SQL `app.query_route_envelope` must match
`smart_rag_core.query_admission.ceilings`.

`no_retrieval` and `scoped_refusal` have no sixth signed deadline. Packet 1
uses the Hybrid 25-second envelope for both.

## Per-call caps by usage kind

| Kind | USD cap | Max prompt tokens | Max completion tokens |
| --- | --- | --- | --- |
| profile | 0.08 | 4000 | 1500 |
| rewrite | 0.08 | 4000 | 1500 |
| embedding | 0.02 | 8000 | 0 |
| lightrag | 0.25 | 8000 | 2000 |
| rerank | 0.20 | 12000 | 2000 |
| answer | 0.40 | 8000 | 2000 |
| summary | 0.25 | 6000 | 1500 |
| verifier | 0.20 | 4000 | 1000 |

Timeout-after-send records the kind cap. The attempt is never under-counted.

Successful sends record provider-reported prompt and completion tokens on
`llm_usage` when a durable consume ran. Retrieve-time Hybrid embed/rerank
and LightRAG query callbacks also add those actuals to
`QueryRetrieveBudget.prompt_tokens` / `completion_tokens` even when the
durable path is unbound, then company-scope and correction write the
ledger onto LangGraph state. Ask Run Details reads the SSE `usage` event
emitted after verify, which is that accumulated run total (profile,
search, answer, verifier). Ask Run Details shows that as **This run**. Durable billed totals also
come from `app.summarize_run_usage` (creator-only) which recomputes USD
from stored token counts using pinned OpenAI list prices
(`gpt-4o-mini` chat, `text-embedding-3-large` embeddings). Account and
admin surfaces use `app.summarize_caller_usage` and
`app.summarize_company_usage`. Migrations:
`20260827180000_summarize_run_usage_v1.sql`,
`20260827190000_summarize_run_usage_token_pricing_v1.sql`,
`20260827200000_summarize_account_usage_token_pricing_v1.sql`.
**This chat** adds earlier questions in the live session plus
conversation-title generation (`POST /conversations/{id}/title`). Title
tokens are not reserved against the query-run envelope.

Retrieve-time batched query embedding (`embedding`), OpenAI rerank
(`rerank`), and LightRAG query callbacks (`lightrag` or `embedding`)
consume the same run-local reservation through
`execute_counted_model_call` (or the same reservation RPCs on the async
LightRAG loop). Remaining model calls decrement. If remaining USD cannot
cover the kind cap, retrieve fails closed and does not call the provider.
Call ceilings already include those retrieve slots (Hybrid 7 includes
embed + rerank). Envelope USD stays `model_call_ceiling ×` the family max
kind cap and is not enlarged.

LangGraph `remaining_model_calls` starts at the family ceiling, decrements
on the profile consume, then `execute_branches_node` / correction retrieve
pass that remaining into `QueryRetrieveBudget` and write the post-retrieve
value back. Later answer/verifier/tool nodes must not restart from the
original ceiling. Each durable consume increments
`budget_reservations.optimistic_version`. `prepare_query`, retrieve, and
answer write the new version onto `authorized_runtime`. The next
`execute_counted_model_call` must send that version; a stale `1` after
profile is `optimistic_version_conflict` and surfaces as a generic run
failure. Durable USD fail-closed remains `execute_counted_model_call`
against the reservation.

## Route envelopes

Envelope USD = `model_call_ceiling × family per-call USD cap`. The family
per-call cap is the conservative maximum kind used on that route (answer
0.40 except inspection 0.25).

| Family | Deadline s | Model calls | Tools | Envelope USD | Prompt tokens | Completion tokens |
| --- | --- | --- | --- | --- | --- | --- |
| hybrid | 25 | 7 | 4 | 2.80 | 56000 | 14000 |
| combined | 45 | 8 | 4 | 3.20 | 64000 | 16000 |
| structured_table | 30 | 6 | 4 | 2.40 | 48000 | 12000 |
| composite | 50 | 9 | 5 | 3.60 | 72000 | 18000 |
| graph_inspection | 10 | 3 | 4 | 0.75 | 12000 | 4500 |
| no_retrieval | 25 | 7 | 4 | 2.80 | 56000 | 14000 |
| scoped_refusal | 25 | 7 | 4 | 2.80 | 56000 | 14000 |
| web_research | 50 | 5 | 5 | 2.00 | 40000 | 10000 |

Shared ceilings: `recursion_limit=24`, 1 correction (0 on `web_research`),
3 subquestions, 1 discovery round, 3 optional manifests, 1 side-effecting
tool. Hybrid call 7 includes batched query embed, one rerank, and
answer-class headroom (profile/answer/verifier/correction). Combined 8 adds
LightRAG consume. Forced Web reserves `web_research` and must fit inside
Composite when Auto later selects Web. A Web plan never Hybrid-clamps.

Monthly query spend uses
`COALESCE(profile.monthly_llm_budget_usd, company.monthly_llm_budget_usd, 200)`.
`graph_maintenance` (QT-COST-003) is not consumable by query.

Auto chat still reserves the Composite envelope once
([QUERY_ADMISSION.md](./QUERY_ADMISSION.md)). Strict-split general and
user-text answers consume that same reservation as `usage_kind=answer`
and write one immutable usage row. Standalone greetings and bounded small talk
normally consume one `usage_kind=profile` classification call plus one
`usage_kind=answer` general-chat call. Profile failure/low confidence records a
typed degradation reason and may consume one general answer call; it does not
authorize retrieval or company claims. Genuine mixed-scope clarifications make
zero answer/verifier calls. A company question with no
authorized evidence is a counted refusal on the company path; it does
not spend a second general-knowledge call. Duplicate idempotency keys
and SSE reconnect reuse the existing paid run.

## Related

- [QUERY_ADMISSION.md](./QUERY_ADMISSION.md)
- [QUALITY_TARGETS.md](../QUALITY_TARGETS.md)
- [ADMINISTRATION.md](../frontend/ADMINISTRATION.md)
- [docs index](../README.md)
