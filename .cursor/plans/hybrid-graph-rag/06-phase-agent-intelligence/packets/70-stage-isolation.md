---
phase: 6
packet: 70
status: complete
title: "Run the four-arm isolation experiment and name the owning failure stage."
requirement_ids: [P06-70]
---

# Packet 70 — Run the four-arm isolation experiment and name the owning failure stage.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md),
[`verify-release-gates`](../../../../../.cursor/skills/verify-release-gates/SKILL.md).

Do not load frontend skills.

## Preconditions

- P06-69 label gate is recorded. Branch is
  `fix/honest-rag-accuracy`.
- The 12-question slice has approved gold chunk IDs on the renamed
  canonical version.
- P06-68 diagnostics and `eval_ask_stage_export.py` exist.
- Production remains sample-blind.

## Allowed outputs

- [`scripts/eval_ask_oracle_context.py`](../../../../../scripts/eval_ask_oracle_context.py)
  (evaluator-only)
- Private reports under `.private-eval/`
- Redacted evidence docs with counts only
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Any production retrieval, prompt, profile, or threshold change
- Embedding sample gold in production code or tests
- Opening holdout
- Claiming a stage without measured diagnostics
- Starting Packet 71 before the decision gate is named

## Ordered actions

1. Arm A: production Ask, fresh conversation, P06-68 diagnostics, plus
   one exam-workspace run of the same question (production retriever,
   `cold_bypass`) for the per-channel `gold_loss_histogram`.
2. Arm A-prime: the same question with the book-title clause removed.
   If A-prime retrieves the gold where A does not, selector text is
   corrupting ranking.
3. Arm B: `eval_ask_oracle_context.py` loads approved gold chunks
   through `fetch_authorized_chunk_context` (ACL/current-version
   recheck), builds `HybridPassage`s, and runs the production answer
   plus verifier gateway with `answer_v3`/`verifier_v2` and
   `render_verified_company_answer`. No sample literal enters
   production.
4. Arm C: strict phrase, approved aliases, and blinded human semantic
   fact/support review of Arm A answers.
5. Assign exactly one first-failing stage per case: `label`,
   `profile/route`, `scope/selector`, `index`, `channel_candidate`,
   `fusion/rerank`, `context_fit`, `coverage/correction`, `answer`,
   `verifier/release`, `deadline`, `metric_only`.
6. Record the decision-gate branch in evidence using the rules below.

## Acceptance checks

- Twelve rows have exactly one stage each.
- The histogram is published count-only.
- The gate branch is named.
- Arm B uses ACL/current-version recheck.
- Holdout remains sealed.

## Negative tests

- Assigning two first-failing stages to one case fails.
- Tuning production from this packet fails.
- Claiming a majority without the 12-row histogram fails.

## Stop routes

- Stop if Arm B cannot run with ACL recheck.
- Stop if a case lacks measured diagnostics and would be guessed.
- Do not start Packet 71 until the gate branch is named.

Decision gate:

- Arm B fails → retrieval tuning forbidden; P06-71 repairs
  answer/verifier/release or the gold contract.
- Arm B passes, A-prime passes, A fails → repair only
  scope/selector resolution.
- Arm B passes and gold absent from every channel in A and A-prime →
  repair only candidate/index behavior.
- A channel holds gold but fusion/rerank/MMR/context drops it →
  repair only that selection stage.
- Effective route is not Hybrid for atomic facts while Arm B passes →
  repair only route determinism.
- Semantic support passes but lexical scoring fails → repair only
  private aliases/scoring.
- No clear majority → earliest stage with the largest count, then
  rerun this slice before expanding.

## Required evidence

Create
[`p06-70-stage-isolation-2026-09-21.md`](../../../../../docs/development/phase-06/p06-70-stage-isolation-2026-09-21.md)
and append to the Phase 6 evidence index: 12-row first-fail histogram,
named gate branch, Arm B ACL-recheck proof, `holdout_opened=false`.

Commands:

```powershell
uv run python scripts/check.py --tier docs
git diff --check
```
