---
phase: 6
packet: 10
status: pending
title: "Implement typed knowledge-scope classification, the live profile gateway, and deterministic route compilation."
requirement_ids: [P06-10]
---

# Packet 10 — Implement typed knowledge-scope classification, the live profile gateway, and deterministic route compilation.

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
- Additive query-profile gateway request/response/schema/version fields,
  `gateways/openai_profile.py`, deterministic mock profile behavior, redacted
  profile tracing, agent runtime/dependency bindings, and their tests.
- Additive `ScopeDegradationReason` on the scope decision, preparation, plan,
  and graph state. The reason is server-derived and never model-supplied.
- Later explicit graph topology/node files required to execute the compiled
  company/general/mixed/fail-closed paths; route-family semantics stay here.
- 2026-09-09 Hybrid PDF overlay (markdown-authorized here; implement in this
  packet after Packet 9 acceptance, not as an out-of-order Phase 6 code run):
  bounded `requested_sources` on the single preparation call; server-side
  authorized title/filename/alias resolver; `ResolvedRetrievalScope`; production
  `rerank_pool` binding on `ProcessHybridRetriever`; Packet 11/12 core
  protocol forwarding (variants + scope) in `DsnBm25Retriever` /
  `ProcessHybridRetriever`; `authorized_chunk_loader` forwarded through
  `RunScopedHybrid`. Until Phase 4 Packet 16 freeze, runtime must fail closed
  to `hybrid_default_v1`. Do not edit `eval_judge_v1.md`.

## Forbidden outputs

- General answer generation, Studio-live authentication/admission, SSE
  lifecycle, or frontend code. The dedicated OpenAI profile adapter and
  profile runtime binding are permitted.
- A new `GeneralChat` route family.
- A second preparation model call.
- Treating the isolated word `policy` as a company signal.
- Changing `StudioQueryState.messages`.
- Editing `eval_judge_v1.md` or executing unfrozen `hybrid_long_document_v1`.

## Ordered actions

1. Add `KnowledgeScope`, `NoRetrievalAnswerMode`, and:

   ```python
   class ScopeDegradationReason(StrEnum):
       PROFILE_UNAVAILABLE = "profile_unavailable"
       PROFILE_MALFORMED = "profile_malformed"
       PROFILE_LOW_CONFIDENCE = "profile_low_confidence"

   class KnowledgeScopeDecision(BaseModel):
       knowledge_scope: KnowledgeScope
       confidence: float = Field(ge=0.0, le=1.0)
       company_signal: bool
       general_signal: bool
       scope_degradation_reason: ScopeDegradationReason | None = None
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
3. A full-message greeting or bounded small-talk message requires the existing
   one structured preparation call; it is not settled by a canned
   deterministic response.
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
9. If the preparation model is unavailable, invalid, or has confidence below
      `0.80`, return `GENERAL_KNOWLEDGE` with a server-derived
      `ScopeDegradationReason` and confidence/provenance retained where valid.
      This is not ambiguity and cannot authorize company evidence.
   10. In deterministic mock mode, use fixed fixtures/heuristics for
       “What is the capital of France?” and “Explain photosynthesis” →
       `GENERAL_KNOWLEDGE`; “What is the status of INV-SR-1001?” and
       “What is our refund period?” → `COMPANY_DOCUMENTS`.

3. Keep existing route families. Map:
   - `COMPANY_DOCUMENTS`: existing matrix unchanged;
     `phase6_extension` is `NONE` or `GRAPH_INSPECTION`;
     `no_retrieval_answer_mode=None`; citations/evidence remain required.
   - `DETERMINISTIC`: `Phase6Extension.NO_RETRIEVAL` and
     `NoRetrievalAnswerMode.GENERAL_MODEL`.
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
   QueryPreparation.scope_degradation_reason: ScopeDegradationReason | None
   RetrievalPlan.knowledge_scope: KnowledgeScope
   RetrievalPlan.no_retrieval_answer_mode: NoRetrievalAnswerMode | None
   RetrievalPlan.scope_degradation_reason: ScopeDegradationReason | None
   QueryGraphState.knowledge_scope: str | None
   QueryGraphState.no_retrieval_answer_mode: str | None
   QueryGraphState.scope_degradation_reason: str | None
   ```

   Initialize the three graph-state fields to `None` in `pending_query_state()`
   and copy them from preparation/plan in existing nodes.
6. Add strict query-profile transport for all `PreparationModelPayload` fields.
   Requests carry pinned prompt text/model ID, bounded remaining deadline, and
   bounded delimited memory. Responses carry one JSON payload, request ID,
   non-negative token counts, `model_calls=1`, and
   `retrieval_performed=False`. JSON Schema uses
   `additionalProperties=false`, existing enum values, and max-three bounds.
7. Add the live OpenAI profile adapter with prompt SHA/version verification,
   model allow-list, bounded timeout, `max_retries=0`, `store=False`, strict
   schema response, no tools, typed failures, and redacted tracing. Reuse the
   approved profile model ID; do not add a model or usage kind.
8. Make the mock profile adapter return a deterministic schema-valid payload
   and prove no DNS/provider construction.
9. Bind `model_caller`, profile prompt text, and actual profile model ID in
   production FastAPI/live Studio dependencies while local `query_studio`
   stays unbound. Malformed payload raises so preparation records
   `profile_malformed`; no fabricated profile is allowed.
10. Write the required unit and contract tests listed in Acceptance checks.
11. Hybrid PDF overlay after Packet 9 acceptance: extend the single
    preparation/profile operation with bounded textual `requested_sources`
    and source-span/confidence/provenance. The model may name text but never a
    document UUID, retrieval limit, SQL predicate, or profile number.
12. Add a server-side resolver over current authorized title/filename/approved
    aliases. Resolve to a hard version filter only when exactly one current
    authorized version matches. Zero matches stay unscoped; multiple matches
    return clarification. Missing and unauthorized IDs remain indistinguishable.
13. Produce `ResolvedRetrievalScope` (version, whole-document/section/page,
    representative-passage count, query class, eligibility, candidate profile
    id). Long profile is eligible only when exactly one version resolves,
    passage count > 5, and the frozen selector allow-lists the class. Until
    Phase 4 Packet 16 freeze, fail closed to `hybrid_default_v1`.
14. In `deps_factory.py`, load `model_gateway` and `rerank_v1` and pass them to
    `ProcessHybridRetriever`. Build a run-local closure around
    `rerank_pool`. Do not store per-run budget on process-global state.
15. Update `DsnBm25Retriever` and `ProcessHybridRetriever` to pass bounded
    query variants and server-resolved scope through Phase 4 Packet 11/12
    core protocols. Forward `authorized_chunk_loader(caller)` through
    `RunScopedHybrid`. Do not reimplement ranking in `apps/agents/`.
16. Expose safe diagnostics: profile id/hash, source-resolution, rerank
    model/prompt hash, requested/called/skipped/fallback, usage/cost.
    Keep `LANGSMITH_EXPORT_IO=false`. Do not edit `eval_judge_v1.md`.

## Acceptance checks

- Full greeting/small talk → one profile call and a usable general scope result.
- “What can you do?” → `GENERAL_KNOWLEDGE`.
- Capital of France / photosynthesis → `GENERAL_KNOWLEDGE`.
- Rewrite with supplied text → `USER_SUPPLIED_TEXT`.
- Invoice ID, `our`, document, table, relationship, broad summary, and graph
  inspection → `COMPANY_DOCUMENTS`.
- Greeting prefix plus company question → `COMPANY_DOCUMENTS`.
- Mixed general+company question → `AMBIGUOUS`.
- Low-confidence, invalid, or unavailable scope output → typed degraded
  `GENERAL_KNOWLEDGE`, never `AMBIGUOUS`.
- Company guard overrides a malicious model result of `GENERAL_KNOWLEDGE`.
- No second preparation model call.
- General/ambiguous plans have no retrieval branches.
- All existing Hybrid/Combined/Table route rows remain unchanged.
- Query-profile live/mock adapters satisfy prompt/model/schema/timeout/retry/
  storage/network/redaction controls and record the actual model ID.
- A genuine mixed decision has no degradation reason; degraded scope has one
  and keeps `company_claim_forbidden=True`.
- Hybrid PDF overlay: a non-trivial two-candidate production Hybrid query calls
  the model gateway exactly once and returns `rerank_call_count=1`; trivial
  exact lookup may skip with the named reason; timeout/refusal/malformed IDs/
  budget denial preserve deterministic RRF; source ambiguity never hard-filters
  or leaks IDs; concurrent runs isolate budgets; mock/identity cannot satisfy
  the live-rerank gate. Unfrozen `hybrid_long_document_v1` remains runtime-denied.

Run at minimum:

```powershell
uv run pytest tests/unit/test_knowledge_scope.py tests/unit/test_query_routing_matrix.py tests/contract/test_query_preparation.py -q
uv run ruff check packages/core/src/smart_rag_core/query_routing apps/agents/src/smart_rag_agents/query/state.py tests/unit/test_knowledge_scope.py
uv run pyright packages/core/src/smart_rag_core/query_routing apps/agents/src/smart_rag_agents/query/state.py tests/unit/test_knowledge_scope.py
```

Also run every existing routing/profile contract suite named by inspection.

## Negative tests

- Isolated `policy` classified as company scope, a second preparation call,
  company questions routed to `GENERAL_MODEL`, profile failure labelled
  `AMBIGUOUS`, model-supplied degradation reason, NoRetrieval without
  `company_claim_forbidden`, a new route family, or mutation of
  `StudioQueryState.messages` fails the packet.
- Hybrid PDF overlay: process-global rerank budget, client-supplied document
  UUIDs/SQL predicates, unfrozen long-document profile execution, or identity
  rerank labelled as a live OpenAI call fails the packet.

## Stop routes

- Stop if the inspected preparation payload cannot carry an additive scope
  field without a second model call, or if existing Hybrid/Combined/Table
  matrix rows would have to change to compile NoRetrieval modes.
- Do not invent a new route family or weaken `company_claim_forbidden`.
- Stop if the profile gateway cannot remain one counted call under existing
  `usage_kind="profile"` caps, strict schema, zero hidden retry, `store=False`,
  and redacted tracing.
- Stop the Hybrid PDF overlay if the provider matrix is unsigned or the current
  OpenAI SDK cannot prove zero hidden retries and strict set equality. Bind and
  verify reranking under `hybrid_default_v1` until Phase 4 Packet 16 freezes
  the long-document selector.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md):
  classification fixtures, degradation reasons, profile adapter/runtime safety,
  model-call counts, actual model ID, unchanged Hybrid/Combined/Table rows,
  exact commands/exit codes, deviations, rollback, and P06-11 handoff.
