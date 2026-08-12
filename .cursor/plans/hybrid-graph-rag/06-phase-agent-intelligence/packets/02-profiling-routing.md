---
phase: 6
packet: 2
status: pending
title: "Implement memory rewrite, extended typed profiling, the complete deterministic route/limitation matrix, one global correction, and bounded parallel branches."
requirement_ids: [P06-02]
---

# Packet 2 — Implement memory rewrite, extended typed profiling, the complete deterministic route/limitation matrix, one global correction, and bounded parallel branches.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

## Preconditions

- Packet 1 is accepted; its authorized runtime, ownership, reservation, deadline, and ceiling context is the only input authority.
- Phase 4 frozen QueryProfile/filter/Hybrid/coverage/section-proof artifacts and Phase 5 GraphRetriever modes, survival/readiness, temporal limitation, ACL-blindness, and precomputed keyword contracts are accepted and inspectable.
- Bounded conversation memory can be loaded by authorized conversation/version without duplicating source documents.

## Allowed outputs

- Query preparation/rewrite/profile schemas and nodes, deterministic allow-listed route planning, bounded decomposition/parallel branch scheduling, correction decision, diagnostics, tests, and evidence under [`apps/agents/src/smart_rag_agents/query/`](../../../../../apps/agents/src/smart_rag_agents/query/).
- No final Combined fusion, answer/verifier, optional catalog, transport, or UI implementation.

## Forbidden outputs

- A catalog-search LLM for core routes, separate rewrite and profiling model calls, production manual routing, more than one correction, more than three subquestions/rewrites, unbounded fan-out, holdout tuning, hidden LightRAG keyword extraction, or graph paths for historical relationships.
- Inferring exhaustive negation from top-k, summarizing a whole document without `section_coverage_ratio=1.0`, interpreting unsupported media, allowing `NoRetrieval` to make company claims, or using graph-only as an answer fallback.

## Ordered actions

1. Load bounded authorized conversation memory and its version; preserve the original query. If a follow-up needs a standalone model rewrite, return it in the same structured preparation call as the profile, persist/display it, score intent/entity fidelity, and retain the original as a fallback variant.
2. Apply input safety and produce one typed `QueryPreparation` containing optional rewrite plus `QueryProfile`: direct-fact/semantic, relationship, multi-hop, broad/global, comparison, structured-table, graph-inspection, non-retrieval, or multi-part; language; UTC/signed-company-timezone temporal intent; high/low-level keywords; entities/approved aliases; exact terms; date/number/metadata filters; negation scope/confidence; document/section/page scope; media intent; historical and low-confidence relationship signals; decomposition need; and confidence.
3. Use no model for simple deterministic profiles. When a model is needed, memory rewrite plus profile consumes at most one gateway call. Normal chat defaults to `Auto`; manual mode is recorded and allowed only on testing/diagnostic surfaces.
4. Build the complete allow-listed matrix:
   - Direct fact/semantic, definition, exact value, policy, date, number, lookup, and ordinary synthesis → `Hybrid`.
   - Current relationship, dependency, connection, impact-chain, cross-entity, and multi-hop → `Combined(Hybrid + LightRAG local/graph-hybrid)`.
   - Explicit past/`as_of` relationship or multi-hop → `Hybrid`, `historical_relationship=true`, and `temporal_graph_limitation`.
   - Broad/global ordinary synthesis → `Hybrid`; corpus-wide theme/landscape → `Combined(GlobalSteering + Hybrid)` with at most three graph theme/entity expansions returning through Hybrid and never becoming evidence.
   - Single-document whole summary → answer only with `section_coverage_ratio=1.0`; otherwise `ScopedRefusal` with uncovered headings/page ranges.
   - Negation/exclusion → scoped Hybrid clarification/evidence, deterministic table/enumeration proof, or `ScopedRefusal`; negation alone never selects Combined or proves a complement.
   - Media-only figure/chart/diagram → signed `ScopedRefusal` unless adjacent caption/OCR satisfies ordinary Hybrid evidence.
   - Comparison → decomposed Hybrid for explicit documents/attributes, Combined for relationships/impact chains, StructuredTable for numeric columns, and composed required branches for mixed cases.
   - Structured aggregation → `StructuredTable`, optionally composed with Hybrid explanatory prose.
   - Explicit graph inspection → `GraphOnlyInspection` through active-workspace/map/current-version/ACL resolution with descriptions reconstructed from canonical passages.
   - Greeting/product help or transformation of user-provided text → `NoRetrieval`, with no company-knowledge claim.
   - Multi-part → at most three subquestions, union required branches, and call the effective route `Composite` when more than one route family is required.
5. Use the original query for simple requests and at most three focused rewrites/subquestions for ambiguous/multi-part requests. Every subquestion inherits packet 1 authorization, reservation, deadline, and ceilings; independent required branches run only within bounded server-controlled parallelism.
6. Invoke Hybrid, LightRAG, StructuredTable, and citation lookup directly from the typed route with precomputed profile keywords and zero catalog-search model calls. Hybrid obeys the shared candidate/recheck/RRF/rerank/MMR/coverage contract.
7. Preserve low-confidence relationship/multi-hop signals when ambiguous and begin with cheaper Hybrid. If frozen query-class `coverage_score` is below its threshold, provisionally `0.65`, spend the single global correction on `Hybrid`→`Combined`, reuse Hybrid candidates, and persist `routing_correction=hybrid_to_combined`.
8. When no relationship signal remains, weak evidence may spend that same single budget on one same-route rewrite/retrieval retry. Never perform both corrections or loop; exhaustion becomes verified partial/insufficient evidence.
9. Persist original/rewrite/profile, requested/effective/corrected route, decomposition/branch plan, coverage and section proof, negation/media/historical flags, manual mode, fallback/limitation/correction reason, and precomputed keyword pass-through for downstream packets.
10. Test every route and mixed example, rewrite fidelity, deterministic/no-model paths, ambiguous escalation, same-route correction, no-second-correction, bounded cancellation, BM25 degradation input, graph unavailability/survival/readiness, and unauthorized ACL-blindness suppression.

## Acceptance checks

- One typed preparation result contains every required field; model-assisted rewrite/profile uses at most one call and preserves intent/entities against the original.
- Every listed route, limitation, refusal, comparison, mixed, and Composite case is deterministic, authorization-preserving, and matches signed route/profile targets.
- Whole-document claims require exactly `section_coverage_ratio=1.0`; the provisional coverage threshold remains `0.65` unless the frozen Phase 4 class value says otherwise; Phase 6 does not retune either.
- Multi-part work has at most three subquestions/rewrites, bounded parallel branches, one global correction total, no hidden catalog or LightRAG keyword call, and safe partial/refusal on exhaustion.
- Historical relationships always stay Hybrid with `temporal_graph_limitation`; graph-only remains inspection; negation/media/no-retrieval cannot escape their evidence/limitation boundaries.

## Negative tests

- Separate rewrite call, profile schema omission, original-query loss, production manual override, fourth subquestion, branch fan-out, second correction, correction loop, hidden keyword/catalog call, holdout-driven threshold change, historical graph path, summary coverage below `1.0`, unproved complement, unsupported media answer, NoRetrieval company claim, unauthorized blindness count, or graph-only answer fails.

## Stop routes

- Stop if frozen Phase 4 profile/coverage artifacts or Phase 5 typed graph signals are absent/incompatible, route behavior cannot be evaluated on disjoint allowed data, or deterministic composition cannot preserve packet 1 authorization/budgets/deadlines.
- Do not invent profile fields, thresholds, graph modes, route labels, or fallback behavior.

## Required evidence

- Append to [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md): preparation schemas/model-call counts, rewrite fidelity, complete route matrix and mixed fixtures, keyword/callback counters, decomposition/parallel bounds, correction traces, coverage/section proofs, limitation/refusal/ACL negatives, exact commands/exit codes, deviations, rollback, and packet 3 handoff.
