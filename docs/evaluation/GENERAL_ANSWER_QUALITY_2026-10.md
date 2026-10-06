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

Filled after the baseline runs in G0 Step 10.

### dev40 (`dev40-g0-baseline`)

| Metric | Count |
| --- | ---: |
| ok | TBD |
| 1_ingestion | TBD |
| 2_retrieval | TBD |
| 3_fusion_pool | TBD |
| 4_rerank_select | TBD |
| 5a_draft_missing | TBD |
| 5b_removed_after_draft | TBD |
| 5_unknown_no_checkpoint | TBD |
| strict passes | TBD/40 |

### holdout40 (`holdout40-g0-baseline`)

| Metric | Count |
| --- | ---: |
| ok | TBD |
| 1_ingestion | TBD |
| 2_retrieval | TBD |
| 3_fusion_pool | TBD |
| 4_rerank_select | TBD |
| 5a_draft_missing | TBD |
| 5b_removed_after_draft | TBD |
| 5_unknown_no_checkpoint | TBD |
| strict passes | TBD/40 |

## After G1a

not run yet

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
