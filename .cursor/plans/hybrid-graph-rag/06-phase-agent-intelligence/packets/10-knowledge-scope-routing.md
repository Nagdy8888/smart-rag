---
phase: 6
packet: 10
status: pending
title: "Implement typed knowledge-scope classification and deterministic NoRetrieval route compilation."
requirement_ids: [P06-10]
---

# Packet 10 — Implement typed knowledge-scope classification and deterministic NoRetrieval route compilation.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skill: [`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).
Do not load frontend, Studio-live, SSE-lifecycle, or answer-generation skills.

## Preconditions

- Packet 9 is recorded in the canonical plan and ADR.
- Existing query-routing models, matrix, preparation, signals, and
  `pending_query_state()` are inspectable.
- Preserve uncommitted `StudioQueryState.messages` and
  `emit_studio_response` work. Do not reset or rewrite Studio chat state.

## Allowed outputs

- New
  [`packages/core/src/smart_rag_core/query_routing/knowledge_scope.py`](../../../../../packages/core/src/smart_rag_core/query_routing/knowledge_scope.py).
- Additive fields on existing routing/profile/state contracts and their tests
  only:
  - [`signals.py`](../../../../../packages/core/src/smart_rag_core/query_routing/signals.py)
  - [`preparation.py`](../../../../../packages/core/src/smart_rag_core/query_routing/preparation.py)
  - [`models.py`](../../../../../packages/core/src/smart_rag_core/query_routing/models.py)
  - [`matrix.py`](../../../../../packages/core/src/smart_rag_core/query_routing/matrix.py)
  - [`__init__.py`](../../../../../packages/core/src/smart_rag_core/query_routing/__init__.py)
  - [`apps/agents/src/smart_rag_agents/query/state.py`](../../../../../apps/agents/src/smart_rag_agents/query/state.py)
  - the existing query-profile prompt/schema only if the inspected structured
    preparation payload supports an additive field.
- Tests in `tests/unit/test_knowledge_scope.py` plus updates to existing
  routing/preparation contract suites.

## Forbidden outputs

- Answer generation, OpenAI adapters, Studio live, SSE lifecycle, or frontend
  code.
- A new `GeneralChat` route family.
- A second preparation model call.
- Treating the isolated word `policy` as a company signal.
- Changing `StudioQueryState.messages`.

## Ordered actions

1. Add `KnowledgeScope`, `NoRetrievalAnswerMode`, and:

   ```python
   class KnowledgeScopeDecision(BaseModel):
       knowledge_scope: KnowledgeScope
       confidence: float = Field(ge=0.0, le=1.0)
       company_signal: bool
       general_signal: bool
   ```

2. Implement `classify_knowledge_scope(...)` with this exact priority:
   1. Compute deterministic company signals: extracted identifiers/codes;
      non-empty document scope; table, relationship, graph-inspection,
      corpus-wide, media, negation, broad-summary, or comparison intent;
      unambiguous company words such as `our`, `my company`, `workspace`,
      `uploaded`, `our documents`, `company knowledge`, or known source IDs;
      do not treat the word `policy` by itself as a company signal;
      bounded recent-memory evidence that an unresolved follow-up refers to a
      prior company-document answer.
   2. Compute deterministic user-text transform only when the user supplied
      the text to transform. “Summarize our policies” is company scope;
      “Rewrite this paragraph: …” is user-supplied text.
   3. A full-message greeting is `DETERMINISTIC`.
   4. Product-help prompts such as “What can you do?” are general-model
      prompts, not the old repeated greeting template.
   5. If both company and general signals exist, return `AMBIGUOUS`.
   6. If a strong company signal exists, return `COMPANY_DOCUMENTS`; this
      always overrides model output.
   7. If a user-text transform exists, return `USER_SUPPLIED_TEXT`.
   8. For remaining natural-language queries, reuse the existing single
      structured preparation call to classify scope. Add the enum/confidence
      to the existing preparation schema and prompt. Extend `_needs_model`
      so unresolved scope requires that same one preparation call even when
      no rewrite/decomposition is needed.
   9. If the preparation model is unavailable, invalid, or has confidence
      below `0.80`, return `AMBIGUOUS`, not general knowledge.
   10. In deterministic mock mode, use fixed fixtures/heuristics for
       “What is the capital of France?” and “Explain photosynthesis” →
       `GENERAL_KNOWLEDGE`; “What is the status of INV-SR-1001?” and
       “What is our refund period?” → `COMPANY_DOCUMENTS`.

3. Keep existing route families. Map:
   - `COMPANY_DOCUMENTS`: existing matrix unchanged;
     `phase6_extension` is `NONE` or `GRAPH_INSPECTION`;
     `no_retrieval_answer_mode=None`; citations/evidence remain required.
   - `DETERMINISTIC`: `Phase6Extension.NO_RETRIEVAL` and
     `NoRetrievalAnswerMode.DETERMINISTIC_CHAT`.
   - `GENERAL_KNOWLEDGE`: `Phase6Extension.NO_RETRIEVAL` and
     `NoRetrievalAnswerMode.GENERAL_MODEL`.
   - `USER_SUPPLIED_TEXT`: `Phase6Extension.NO_RETRIEVAL` and
     `NoRetrievalAnswerMode.USER_TEXT_MODEL`.
   - `AMBIGUOUS`: `Phase6Extension.NO_RETRIEVAL` and
     `NoRetrievalAnswerMode.CLARIFICATION`.
4. For every NoRetrieval mode keep `company_claim_forbidden=True`, one
   `BranchKind.NO_RETRIEVAL`, zero Hybrid/LightRAG/Table tools, and the
   existing `RetrievalPlan` validator that rejects NoRetrieval without
   `company_claim_forbidden`.
5. Add required fields:

   ```python
   QueryPreparation.knowledge_scope: KnowledgeScope
   QueryPreparation.knowledge_scope_confidence: float
   RetrievalPlan.knowledge_scope: KnowledgeScope
   RetrievalPlan.no_retrieval_answer_mode: NoRetrievalAnswerMode | None
   QueryGraphState.knowledge_scope: str | None
   QueryGraphState.no_retrieval_answer_mode: str | None
   ```

   Initialize the two graph-state fields to `None` in `pending_query_state()`
   and copy them from preparation/plan in existing nodes.
6. Write the required unit and contract tests listed in Acceptance checks.

## Acceptance checks

- Full greeting → `DETERMINISTIC`.
- “What can you do?” → `GENERAL_KNOWLEDGE`.
- Capital of France / photosynthesis → `GENERAL_KNOWLEDGE`.
- Rewrite with supplied text → `USER_SUPPLIED_TEXT`.
- Invoice ID, `our`, document, table, relationship, broad summary, and graph
  inspection → `COMPANY_DOCUMENTS`.
- Greeting prefix plus company question → `COMPANY_DOCUMENTS`.
- Mixed general+company question → `AMBIGUOUS`.
- Low-confidence, invalid, or unavailable scope output → `AMBIGUOUS`.
- Company guard overrides a malicious model result of `GENERAL_KNOWLEDGE`.
- No second preparation model call.
- General/ambiguous plans have no retrieval branches.
- All existing Hybrid/Combined/Table route rows remain unchanged.

Run at minimum:

```powershell
uv run pytest tests/unit/test_knowledge_scope.py tests/unit/test_query_routing_matrix.py tests/contract/test_query_preparation.py -q
uv run ruff check packages/core/src/smart_rag_core/query_routing apps/agents/src/smart_rag_agents/query/state.py tests/unit/test_knowledge_scope.py
uv run pyright packages/core/src/smart_rag_core/query_routing apps/agents/src/smart_rag_agents/query/state.py tests/unit/test_knowledge_scope.py
```

Also run every existing routing/profile contract suite named by inspection.

## Negative tests

- Isolated `policy` classified as company scope, a second preparation call,
  company questions routed to `GENERAL_MODEL`, NoRetrieval without
  `company_claim_forbidden`, a new route family, or mutation of
  `StudioQueryState.messages` fails the packet.

## Stop routes

- Stop if the inspected preparation payload cannot carry an additive scope
  field without a second model call, or if existing Hybrid/Combined/Table
  matrix rows would have to change to compile NoRetrieval modes.
- Do not invent a new route family or weaken `company_claim_forbidden`.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md):
  classification fixtures, model-call counts, unchanged Hybrid/Combined/Table
  rows, exact commands/exit codes, deviations, rollback, and P06-11 handoff.
