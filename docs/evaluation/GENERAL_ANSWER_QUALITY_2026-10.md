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

Reverted by stop rule. G4a SHA `05d193d` passed private parse check
(indented_code_elements 0→77, pipe_table_elements 0→24,
code_facts_in_one_element 14/14→14/14, table_facts_in_one_element
14/14→14/14). G4b re-ingest document `90d008d3-2cca-4951-98d4-7fdc5a6d6b27`,
version `580f4450-f0d4-44cc-b22c-3fb985fdbe9e` (`parser_v1_pdf_reflow_v5`,
1,038 chunks; pipe_table_chunks 0→41, indented_line_chunks 0→97).
`dev40-g4` vs last kept `dev40-g1b`: code+table strict 9 vs 11 (must go
up — fail); total strict 9 vs 11 (drop 2 ≤ 3 — pass). p90_wall_seconds
36.875. G4a reverted (`3bc034e`); book re-ingested as document
`ebaa1d17-446d-47f3-9d5c-941d3a45a60a`, version
`940edc86-be9b-4a12-b1bd-64f57d29393a` (`parser_v1_pdf_reflow_v4`,
1,005 chunks).

| Metric | After G1b | After G4 (`dev40-g4`) |
| --- | ---: | ---: |
| ok | 16 | 13 |
| 1_ingestion | 0 | 0 |
| 2_retrieval | 14 | 15 |
| 3_fusion_pool | 5 | 6 |
| 4_rerank_select | 1 | 0 |
| 5a_draft_missing | 5 | 10 |
| 5b_removed_after_draft | 5 | 2 |
| 5_unknown_no_checkpoint | 0 | 0 |
| strict passes | 11/40 | 9/40 |
| code strict | 5 | 5 |
| table strict | 6 | 4 |
| code+table strict | 11 | 9 |
| salvage_overwrite | 0 | 0 |
| refused_after_draft | 5 | 2 |

## Acceptance (G5)

Probe: G1a present, G1b present, G2 MISSING, G3 MISSING. Parser
`parser_v1_pdf_reflow_v4`, chunking `chunking_v2` (G4a not kept after
stop-rule revert). `test_verifier_verbatim_support.py` omitted (G2
reverted). Unit tier / PR checks still fail on pre-existing inventory +
claims-contract tests (not introduced by kept packets).

Kept packets: G0, G1a, G1b. Reverted: G2, G3, G4a (after G4b measure).

| Check | G0 baseline | G5 final | Target | Result |
| --- | --- | --- | --- | --- |
| holdout40 strict passes (runner) | 5/40 | 10/40 | >= 30 and >= G0 | fail |
| holdout40 5a + 5b facts | 15 | 6 | <= floor(G0 / 2) = 7 | pass |
| gold-literal guard | n/a | exit 0 | exit 0 | pass |
| negatives5 refusals | n/a | 5/5 | 5/5 | pass |
| verifier/release/invented tests | n/a | 40 passed | 0 failed | pass |
| holdout40 p90 wall seconds | 45.469 | 32.219 | <= G0 + 5.0 | pass |
| dev40 strict passes (info) | 9/40 | 10/40 | info | - |

### Holdout stages (fact counts)

| Stage | G0 | G5 |
| --- | ---: | ---: |
| ok | 6 | 14 |
| 1_ingestion | 0 | 0 |
| 2_retrieval | 19 | 20 |
| 3_fusion_pool | 4 | 3 |
| 4_rerank_select | 0 | 1 |
| 5a_draft_missing | 4 | 4 |
| 5b_removed_after_draft | 11 | 2 |
| 5_unknown_no_checkpoint | 0 | 0 |

Failed target: holdout40 strict passes 10/40 is above G0 (5/40) but
below the absolute bar of 30/40, so acceptance target 1 fails.
Generation losses (5a+5b) halved as required; salvage_overwrite went to
0 on the holdout.

## Decision

Rejected by the user on 2026-10-07 for a new repair cycle (retrieval
then draft, gpt-4o-mini only). holdout40 retired to
`.private-eval/dev-retired-holdout40-2026-10-v1.json` (original file
also remains; both are now dev data). Next cycle targets stage
`2_retrieval` first (20 facts on `holdout40-g5-final`), then
`5a_draft_missing`. Cycle baselines: `dev40-g5-final` (strict 10/40,
`2_retrieval` 14, `5a` 7) and `spot30-post-g5` (strict 20/30, `5a` 10).

## Cycle 2 — retrieval then draft (2026-10-07)

### Baselines (carried)

| Set | Strict | 2_retrieval | 5a | 5b |
| --- | ---: | ---: | ---: | ---: |
| `dev40-g5-final` | 10/40 | 14 | 7 | 5 |
| `spot30-post-g5` | 20/30 | 1 | 10 | 0 |

### After retrieval-1

not run yet

### After draft-1

not run yet

## Approvals recorded

- 2026-10-06 - G4b re-ingest pre-approved: "no need for my approval make g4b".
- 2026-10-07 - New cycle: retrieval then draft; gpt-4o-mini only.
