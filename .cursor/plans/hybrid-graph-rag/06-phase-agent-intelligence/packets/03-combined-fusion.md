---
phase: 6
packet: 3
status: pending
title: "Implement resolved-path Combined fusion and ablation, deterministic table composition, canonical answer evidence, inference-link citations, and layered verification."
requirement_ids: [P06-03]
---

# Packet 3 — Implement resolved-path Combined fusion and ablation, deterministic table composition, canonical answer evidence, inference-link citations, and layered verification.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

## Preconditions

- Packets 1–2 are accepted; route plans carry authorized runtime, reservation/deadline/cancellation, profile keywords, correction state, and requested/effective route.
- Phase 4 returns the frozen canonical Hybrid evidence/ranks/coverage and deterministic table plan/result provenance; Phase 5 returns bounded resolved application paths and canonical passage support, not native graph prose.
- Relationship/multi-hop development/qualification fixtures and the disjoint immutable holdout protocol are available without exposing holdout labels for tuning.

## Allowed outputs

- Bounded Combined branch execution, resolved-path scoring/fusion, naive-union ablation/fallback decision, deterministic table composition, one canonical answer generation, inference-link citation model, layered verifier, tests, metrics, and evidence.
- Versioned evaluated configuration may retain resolved-path fusion or deliberately select the simpler deduplicated union according to the required ablation.

## Forbidden outputs

- Native graph prose, BM25 snippets, unresolved paths, or model-calculated spreadsheet values as evidence; graph-only answer fallback; an LLM-generated fusion weight; unsupported inference; verifier loops; more than one answer generation; or holdout-based tuning.
- Query-time N-per-link support searches, hidden LightRAG keyword calls, a local reranker, or a requirement that a composed inference appear verbatim in one passage.

## Ordered actions

1. For `Combined`, run authorized Hybrid and LightRAG concurrently within the shared limits. Pass precomputed high/low keywords and choose `local` or graph `hybrid`; GlobalSteering produces at most three theme/entity expansions that return through Hybrid and never receive graph-evidence score.
2. Resolve every LightRAG lead through active workspace, precomputed mapping, survival/readiness, current-version, deletion, graph eligibility, and ACL checks. Discard unsupported candidates. A rejected, unavailable, timed-out, or low-survival graph branch yields `requested_route=Combined`, `effective_route=Hybrid`, and a typed reason; it never fabricates missing relationship evidence.
3. Execute `StructuredTable` only from its validated declarative bounded-sandbox plan and return exact deterministic provenance. Compose its separate evidence type with Hybrid or Combined when the route requires it; never ask the answer model to calculate from prose.
4. Take Hybrid's post-rerank `hybrid_rank`, or RRF rank only for the narrow allowed skip/fallback. For each fully mapped graph path calculate:

   ```text
   path_support =
     min(edge_support_confidence)
     / (1 + 0.25 * (hop_count - 1))

   graph_passage_strength =
     max_over_paths(
       path_support
       * min(1.20, 1 + 0.10 * (distinct_supported_edges_in_passage - 1))
     )
   ```

5. Rank canonical passages by `graph_passage_strength` to obtain `graph_rank`, then calculate:

   ```text
   combined_score(passage) =
       1.00 / (60 + hybrid_rank)
     + 0.50 / (60 + graph_rank)
   ```

   An absent branch contributes zero. The allow-listed graph weight starts at `0.50` and is never model-generated. Apply at most a `1.10` agreement multiplier when a passage ranks in both branches, enforce frozen diversity/document quotas, and cap graph-discovered-only passages at 40% of final evidence units.
6. Evaluate Hybrid-only, naive deduplicated union, and resolved-path fusion on relationship/multi-hop fixtures. Keep fusion only if it beats naive union on answer/path success and citation completeness while meeting Combined cost and latency gates; otherwise ship the simpler union and record why.
7. Generate one answer from canonical Supabase passages plus deterministic table values. For every multi-hop conclusion, represent ordered atomic links, cite each link to one or more canonical passages, label the composed conclusion as inference, and word it no more strongly than the supported path.
8. Verify deterministically first: current source/version/ACL, citation-span or table value/range alignment, and inference-chain link completeness. Then use one separately budgeted small-model call for one structured batch of at most six material atomic links; omit lower-priority claims instead of issuing another verifier call.
9. Remove or refuse unsupported links. A chain whose every link is supported remains a labeled inference even if its composed conclusion does not occur verbatim in one passage. Deadline/step exhaustion emits terminal verified partial/insufficient evidence.
10. Persist candidate/path/fusion scores, canonical chunk/table IDs, atomic-link and ordered inference citations, requested/effective/fallback route, graph mode/survival/readiness, coverage, correction reuse, answer/verifier usage, and safe downstream event payloads.
11. Exercise representative contracts: refund-period fact → Hybrid; Project Atlas product relationships → Combined with resolved canonical support; Atlas-to-Supplier multi-hop → Combined inference; LightRAG loss → visible Hybrid fallback; numeric comparison → deterministic table provenance; unsupported link → removal/refusal.
12. Run the disjoint Combined evaluation and ablation without tuning on holdout labels; append all accuracy, citation, latency, model-call, tool, and cost results.

## Acceptance checks

- Resolved paths contribute only authorized current canonical passages; table outputs identify exact deterministic source cells/ranges; graph prose/BM25 snippets never reach answer evidence.
- The formulas, `0.25` hop penalty, `1.20` edge-support multiplier cap, RRF denominator `60`, graph weight `0.50`, agreement cap `1.10`, and 40% graph-discovered-only cap are exact, deterministic, and fixture-tested.
- Fusion beats naive union on answer/path success and citation completeness within gates or is removed in favor of documented union.
- On the disjoint relationship/multi-hop evaluation, the complete Combined answer path improves success by at least 10 percentage points over Hybrid alone while preserving global citation correctness/completeness, faithfulness, and cost ceilings; first token remains within 10 seconds and completion within 35 seconds at p95.
- One answer call and at most one small verifier call covering no more than six material links produce complete ordered citations; unsupported links are omitted/refused, not softened into uncited claims.

## Negative tests

- Unmapped/stale/deleted/unauthorized path, missing edge support, native description/reference as evidence, graph-only fallback, hidden keyword call, model fusion weight, agreement multiplier above `1.10`, graph-only evidence above 40%, table arithmetic from prose, seventh verifier link triggering another call, unsupported chain, conclusion-verbatim requirement, LightRAG timeout mislabeled Combined, or holdout-tuned configuration fails.

## Stop routes

- Stop if canonical path resolution, deterministic table provenance, disjoint evaluation, or real authorization/current-version boundaries cannot be exercised; if both fusion and naive union miss the signed quality/citation/cost/deadline gates; or if the at-least-10-point Combined gain cannot be proven.
- A failed complex fusion must simplify or block; it cannot be retained by subjective preference.

## Required evidence

- Append to [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md): branch/callback traces, resolver inputs/outputs, formula golden fixtures, Hybrid/union/fusion ablation, 10-point gain calculation, table provenance, atomic-link/verifier batches and call counts, latency/cost/deadline/fallback results, exact commands/exit codes, selected algorithm/config hash, deviations, rollback, and packet 4 handoff.
