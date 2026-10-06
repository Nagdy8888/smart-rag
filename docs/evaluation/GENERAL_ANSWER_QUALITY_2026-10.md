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

Kept. Guard exits 0. Retrieval-stage sum did not grow; strict drop ≤ 3.

| Metric | After G1a | After G1b |
| --- | ---: | ---: |
| ok | 16 | 16 |
| 1_ingestion | 0 | 0 |
| 2_retrieval | 15 | 14 |
| 3_fusion_pool | 6 | 5 |
| 4_rerank_select | 2 | 1 |
| 5a_draft_missing | 4 | 5 |
| 5b_removed_after_draft | 3 | 5 |
| 5_unknown_no_checkpoint | 0 | 0 |
| strict passes | 12/40 | 11/40 |
| retrieval stage sum (2+3+4) | 23 | 20 |
| salvage_overwrite | 0 | 0 |
| refused_after_draft | 3 | 5 |
| gold-literal guard | FAIL rerank only | exit 0 |

## After G2

Reverted by stop rule. Target `5b_removed_after_draft` /
`refused_after_draft`+`trimmed_or_rewritten` stayed flat (5 → 5).
Strict delta 0. Probe before revert: G1a/G1b/G2 present. Image rebuilt
for live proof: yes (G2 present). p90_wall_seconds 33.015.

| Metric | After G1b | After G2 |
| --- | ---: | ---: |
| ok | 16 | 16 |
| 1_ingestion | 0 | 0 |
| 2_retrieval | 14 | 15 |
| 3_fusion_pool | 5 | 5 |
| 4_rerank_select | 1 | 1 |
| 5a_draft_missing | 5 | 4 |
| 5b_removed_after_draft | 5 | 5 |
| 5_unknown_no_checkpoint | 0 | 0 |
| strict passes | 11/40 | 11/40 |
| salvage_overwrite | 0 | 0 |
| refused_after_draft | 5 | 5 |
| trimmed_or_rewritten | 0 | 0 |

## After G3

Gate: continue (`5a_draft_missing=4` on `dev40-g2`, threshold ≥3).
Reverted by stop rule. Target `5a_draft_missing` stayed flat vs kept
baseline `dev40-g1b` (5 → 5). Strict +1. Locate `ran:None=33`,
`failed:deadline_exhausted=7`, `quotes_total=42`. Image rebuilt for
live proof: yes (G3 present). p90_wall_seconds G3=44.093, G2=33.015.

| Metric | After G1b | After G3 |
| --- | ---: | ---: |
| ok | 16 | 17 |
| 1_ingestion | 0 | 0 |
| 2_retrieval | 14 | 14 |
| 3_fusion_pool | 5 | 4 |
| 4_rerank_select | 1 | 2 |
| 5a_draft_missing | 5 | 5 |
| 5b_removed_after_draft | 5 | 4 |
| 5_unknown_no_checkpoint | 0 | 0 |
| strict passes | 11/40 | 12/40 |
| salvage_overwrite | 0 | 0 |
| refused_after_draft | 5 | 4 |
| trimmed_or_rewritten | 0 | 0 |

## After G4

G4a tried; reverted by stop rule before commit (working tree restored).
Private parse check: indented_code_elements 0→77, pipe_table_elements
0→24, but code_facts_in_one_element 14/14→13/14 and
table_facts_in_one_element 14/14→13/14 (must not drop). No G4a SHA.
G4b skipped: depends on G4a committed with passing parse check.

## Acceptance (G5)

not run yet
