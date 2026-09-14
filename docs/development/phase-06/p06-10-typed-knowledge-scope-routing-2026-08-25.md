# P06-10 — Typed knowledge-scope routing (accepted 2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: classify `KnowledgeScope` with the approved priority, compile
existing route families plus NoRetrieval answer modes, bind the live profile
gateway, and apply the Hybrid PDF overlay (requested sources, server-side
`ResolvedRetrievalScope`, production `rerank_pool` on `ProcessHybridRetriever`).
No answer generation, Studio live, SSE lifecycle, or frontend edits.

User directed continuous execution after P06-27 on 2026-09-10, so this
packet is recorded accepted from the proven gates below rather than a
separate wait step.

## Plan requirement

Quote: implement typed knowledge-scope classification, the live profile gateway,
and deterministic route compilation.

## Classification proven

| Query | Scope | Route / mode |
| --- | --- | --- |
| `Hi` / `Hello` | `general_knowledge` | NoRetrieval / `general_model` |
| `What can you do?` | `general_knowledge` | NoRetrieval / `general_model` |
| capital of France / photosynthesis | `general_knowledge` | NoRetrieval / `general_model` |
| `Rewrite this paragraph: …` | `user_supplied_text` | NoRetrieval / `user_text_model` |
| invoice / `our` / document / table / relationship / summary / graph | `company_documents` | existing matrix; mode `None` |
| `Hi, what is our refund period?` | `company_documents` | Hybrid |
| France + our refund | `ambiguous` | NoRetrieval / `clarification` |
| Isolated `policy` | not a company signal | not `COMPANY_DOCUMENTS` |
| low-confidence / invalid / unavailable profile | `general_knowledge` with `ScopeDegradationReason` | never `AMBIGUOUS` |
| company + malicious `GENERAL_KNOWLEDGE` | `company_documents` | company guard wins |
| Genuine mixed | `ambiguous` | no degradation reason |

Degraded general scope keeps `company_claim_forbidden=True`. Existing
Hybrid/Combined/Table/inspection/media matrix rows remain company scope with
no NoRetrieval mode.

## Hybrid PDF overlay proven

- Bounded `requested_sources` on the single preparation call.
- `ResolvedRetrievalScope` in `packages/core/src/smart_rag_core/retrieval/source_scope.py`.
- `ProcessHybridRetriever` receives `model_gateway` and `rerank_v1` text
  from `deps_factory.py` and builds a run-local `rerank_pool` closure.
- Unfrozen `hybrid_long_document_v1` stays runtime-denied
  (`FROZEN_LONG_DOCUMENT_PROFILE_SHA256` is empty).
- `eval_judge_v1.md` was not edited. `StudioQueryState.messages` was not mutated.

## Verification

| Command | Exit |
| --- | --- |
| `uv run pytest tests/unit/test_knowledge_scope.py tests/unit/test_query_routing_matrix.py tests/unit/test_query_routing_preparation.py tests/unit/test_query_profile.py tests/unit/test_query_profile_gateway.py tests/unit/test_hybrid_rerank.py tests/contract/test_hybrid_rerank.py -q` | 0 (skips only hosted/live contract cells) |
| `uv run pytest tests/unit/test_pdf_hybrid_overlay.py tests/unit/test_query_graph_runtime.py tests/unit/test_query_routing_preparation.py -q` | 0 |
| `uv run ruff check packages/core/src/smart_rag_core/query_routing apps/agents/src/smart_rag_agents/query/state.py tests/unit/test_knowledge_scope.py` | 0 |
| `uv run pyright packages/core/src/smart_rag_core/query_routing/knowledge_scope.py packages/core/src/smart_rag_core/query_routing/preparation.py apps/agents/src/smart_rag_agents/query/state.py tests/unit/test_knowledge_scope.py` | 0 |

Unverified: live OpenAI preparation-model scope quality on real company text.

## Rollback

Remove `knowledge_scope.py` overlay fields, restore `_needs_model` /
profile schema, and unbind `ProcessHybridRetriever` rerank/scope wiring.
Do not freeze `hybrid_long_document_v1` as a rollback step.

## Handoff

Next coding packet is
[P06-28](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/28-eval-quiz-case-database.md)
(hosted quiz-case schema and `app_api` RPCs). Do not start P06-11 until
P06-28 through P06-36 close.
