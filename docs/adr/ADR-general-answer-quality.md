---
title: ADR - General answer-quality repair
adr_id: ADR-general-answer-quality
status: proposed
owner: engineering-lead
last-reviewed: 2026-10-06
audience: engineering, reviewers
---

# ADR: General answer-quality repair

## Status

`proposed`; becomes accepted when the user accepts G5.

## Context

Every fresh set scored about 60%. On 130 first-time facts the draft held
104 and the release 80; 13 correct drafts were overwritten by
question-specific salvages; 13 correct claims were rejected by the
verifier; salvages repaired 2. Earliest-stage losses on 275 facts over 6
first-time runs: generation 100, rerank/select 28, retrieval 9, fusion
pool 5, ingestion 1.

## Decision

1. Delete question-specific salvage, promotion, and seed code and the
   matching prompt bullets (`answer_v6`). Keep only structural repairs:
   named code definition, named table block, requested shape.
   Done in G1a (answer side) on 2026-10-06. Retrieval side done in G1b
   on 2026-10-06.
2. A verifier "unsupported" verdict does not remove a fact claim whose
   normalized text is a verbatim substring (at least 12 characters) of
   a cited passage. Tried in G2 on 2026-10-06; reverted by stop rule
   (`refused_after_draft`+`trimmed_or_rewritten` stayed flat at 5 on
   `dev40-g2` vs `dev40-g1b`).
3. Optional (G3, only if the stage report justifies it): one
   `locate_v1` gpt-4o-mini call before the answer call, recorded under
   the existing `usage_kind = "answer"` so no migration is needed, and
   skipped when it would consume the answer-stage reserve. Tried in G3
   on 2026-10-06; reverted by stop rule (`5a_draft_missing` stayed flat
   at 5 on `dev40-g3` vs `dev40-g1b`; locate `ran:None=33`).
4. PDF reflow keeps line breaks and indentation for monospace code
   lines and rebuilds captioned (or page-continued) tables as Markdown
   pipe tables from line geometry (`parser_v1_pdf_reflow_v5`); the
   prose splitter keeps paragraphs with single newlines whole up to
   536 tokens and otherwise splits them at line ends, repeating a pipe
   table's header (`chunking_v3`).
5. Fixed measurement loop with dev40 and sealed holdout40 and a stop
   rule (see the runbook).

## Alternatives considered

- A larger model (rejected: user requires gpt-4o-mini).
- Keeping salvages and adding more (rejected: does not transfer).
- A second verifier call (rejected: `MAX_VERIFIER_CALLS = 1` contract).
- A new `usage_kind` for locate (rejected: needs a migration of
  `app.llm_usage.llm_usage_kind_allowed`).

## Acceptance targets

1. holdout40 strict passes at least 30 of 40, and not below the G0
   holdout baseline.
2. holdout40 generation losses (`5a_draft_missing` +
   `5b_removed_after_draft`) at most half of the G0 holdout count
   (round down).
3. `scripts/check_gold_literals.py` exits 0.
4. negatives5: 5 of 5 answers have status `insufficient_evidence`.
5. Verifier, release, and invented-expansion unit tests pass.
6. p90 wall seconds on holdout40 at most 5.0 s above the G0 holdout p90.

## Consequences

Scores on older tuned sets drop; latency p90 may grow by up to 5 s if G3
runs; re-ingest needed for G4 (G4b).

## Rollback

Revert the packet commits; for G4 also follow the re-ingest rollback in
G4b.

## Approvals recorded

gpt-4o-mini only; up to 2 answer-stage calls per question (user,
2026-10-06).
