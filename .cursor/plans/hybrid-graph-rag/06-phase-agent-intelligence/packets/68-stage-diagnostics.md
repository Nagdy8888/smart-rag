---
phase: 6
packet: 68
status: complete
title: "Persist ID-only Hybrid branch diagnostics and de-hardcode promotion inputs."
requirement_ids: [P06-68]
---

# Packet 68 — Persist ID-only Hybrid branch diagnostics and de-hardcode promotion inputs.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md),
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

Do not load frontend skills.

## Preconditions

- P06-67 canonical copy is recorded. Branch is
  `fix/honest-rag-accuracy`.
- [`BranchResult`](../../../../../packages/core/src/smart_rag_core/query_routing/models/results.py)
  persists only `ranked_ids`, `coverage_score`, `fallback_reason`.
  `HybridRunResult` already carries channel IDs that are dropped before
  checkpointing.
- [`run_company_ask.py`](../../../../../scripts/run_company_ask.py)
  hard-codes `source_resolution=unscoped`,
  `bm25_degraded_explicit=True`, and `rerank_accounting_ok=True`.

## Allowed outputs

- Frozen `HybridBranchDiagnostics` and optional
  `BranchResult.hybrid_diagnostics`
- Population from `HybridRunResult` in
  [`hybrid.py`](../../../../../packages/core/src/smart_rag_core/query_routing/branch_channels/hybrid.py)
- [`scripts/eval_ask_stage_export.py`](../../../../../scripts/eval_ask_stage_export.py)
- Updates to `run_company_ask.py`, `rescore_company_ask.py`,
  [`accuracy_promotion.py`](../../../../../packages/core/src/smart_rag_core/evaluation/accuracy_promotion.py),
  [`test_accuracy_promotion.py`](../../../../../tests/unit/test_accuracy_promotion.py),
  [`tests/unit/test_hybrid_branch_diagnostics.py`](../../../../../tests/unit/test_hybrid_branch_diagnostics.py),
  and [`DUAL_METRIC_SCORING.md`](../../../../../docs/evaluation/DUAL_METRIC_SCORING.md)
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- New SSE fields
- Any passage, query, title, snippet, answer, or source text in
  diagnostics
- Changes to retrieval ranking, coverage, correction, or prompts
- Favorable defaults for missing promotion fields
- Starting Packet 69 gold work

## Ordered actions

1. Add frozen `HybridBranchDiagnostics` and optional
   `BranchResult.hybrid_diagnostics`: `source_resolution`,
   `retrieval_profile_id`, `fallback_reason`, `rerank_fallback`,
   `rerank_call_count`, `embedding_call_count`, `first_evidence_ms`,
   `dense_ids[:100]`, `bm25_ids[:75]`, `term_ids[:30]`,
   `fused_ids[:100]`, `selected_ids[:12]`, coverage components,
   `effective_route`. UUID strings only. Populate from
   `HybridRunResult` in `branch_channels/hybrid.py`.
2. Unit tests: no text field exists; caps enforced; serialization
   deterministic; `BranchResult` without diagnostics still validates.
3. `eval_ask_stage_export.py`: for each recorded `run_id`, read
   checkpoint diagnostics and `llm_usage` (`usage_kind in
   ('embedding','rerank')`), emit a private JSON of stage fields plus
   `unknown` for anything missing. `rerank_accounting_ok` per run =
   embedding row present and (rerank row present or named
   `rerank_fallback`). `bm25_degraded_explicit` =
   `fallback_reason` names BM25 whenever BM25 was unavailable.
4. Remove from `run_company_ask.py`: `source_resolution=UNSCOPED`,
   `fused_count = citation_count`, `retrieval_empty` heuristic,
   `bm25_degraded_explicit=True`, `rerank_accounting_ok=True`. The
   runner records `run_id` per question and joins the export.
   Effective route comes from checkpoint state, never
   `runs.route_family`.
5. Add `unknown_required_fields: int` to `decide_accuracy_promotion`;
   any positive count appends `unknown_required_fields` and blocks
   promotion. Test it.

## Acceptance checks

- Diagnostics contain UUIDs and bounded numeric/enumerated metadata
  only.
- A three-question run yields measured `source_resolution`, channel
  IDs, `fallback_reason`, `rerank_fallback`, profile id, and
  accounting flags with zero `unknown`.
- Missing required fields block promotion.
- Backward-compatible checkpoints without diagnostics still validate.

## Negative tests

- A text field on `HybridBranchDiagnostics` fails.
- Hardcoded `bm25_degraded_explicit=True` or
  `rerank_accounting_ok=True` remaining in the runner fails.
- Promotion with `unknown_required_fields > 0` fails.

## Stop routes

- Stop if diagnostics would persist source text.
- Stop if a required field cannot be measured and would be replaced
  with a favorable default.
- Do not change retrieval behavior to make diagnostics look complete.

## Required evidence

Create
[`p06-68-stage-diagnostics-2026-09-21.md`](../../../../../docs/development/phase-06/p06-68-stage-diagnostics-2026-09-21.md)
and append to the Phase 6 evidence index: field list, cap proof, three
run IDs with measured flags, promotion unknown-field test, commands,
rollback (drop the optional diagnostics field and restore prior
runner).

Commands:

```powershell
uv run python -m pytest tests/unit/test_hybrid_branch_diagnostics.py tests/unit/test_accuracy_promotion.py -q
uv run python scripts/check.py --tier docs
git diff --check
```
