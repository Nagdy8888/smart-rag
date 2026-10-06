---
title: General answer-quality repair evidence
owner: engineering-lead
status: draft
last-reviewed: 2026-10-06
audience: eng, reviewers
---

# General answer-quality repair evidence

Counts only. Private questions, gold phrases, and answer text stay under
`.private-eval/`.

## Sets

| Set | Size | Kind mix (target) | Role |
| --- | ---: | --- | --- |
| `dev40-2026-10-v1` | 40 | ~14 code / ≤12 table / rest text | debug and tune |
| `holdout40-2026-10-v1` | 40 | ~14 code / ≤12 table / rest text | sealed; G0 + G5 only |

## Baseline (G0)

### dev40 (`dev40-g0-baseline`)

| Metric | Count |
| --- | ---: |
| ok | 14 |
| 1_ingestion | 0 |
| 2_retrieval | 15 |
| 3_fusion_pool | 7 |
| 4_rerank_select | 0 |
| 5a_draft_missing | 6 |
| 5b_removed_after_draft | 4 |
| 5_unknown_no_checkpoint | 0 |
| strict passes | 9/40 |
| p90 wall seconds | 54.078 |
| removed causes | salvage_overwrite=4 |

### holdout40 (`holdout40-g0-baseline`)

| Metric | Count |
| --- | ---: |
| ok | 6 |
| 1_ingestion | 0 |
| 2_retrieval | 19 |
| 3_fusion_pool | 4 |
| 4_rerank_select | 0 |
| 5a_draft_missing | 4 |
| 5b_removed_after_draft | 11 |
| 5_unknown_no_checkpoint | 0 |
| strict passes | 5/40 |
| p90 wall seconds | 45.469 |
| removed causes | salvage_overwrite=10, refused_after_draft=1 |

## After G1a

Kept. Target `5b_removed_after_draft` / `salvage_overwrite` improved.

| Metric | G0 baseline | After G1a |
| --- | ---: | ---: |
| ok | 14 | 16 |
| 1_ingestion | 0 | 0 |
| 2_retrieval | 15 | 15 |
| 3_fusion_pool | 7 | 6 |
| 4_rerank_select | 0 | 2 |
| 5a_draft_missing | 6 | 4 |
| 5b_removed_after_draft | 4 | 3 |
| 5_unknown_no_checkpoint | 0 | 0 |
| strict passes | 9/40 | 12/40 |
| salvage_overwrite | 4 | 0 |
| refused_after_draft | 0 | 3 |

## After G1b

not run yet

## After G2

not run yet

## After G3

not run yet

## After G4

not run yet

## Acceptance (G5)

not run yet
