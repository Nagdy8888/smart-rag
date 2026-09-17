---
phase: 6
packet: 59
status: pending
title: "Create a tested, private-safe dual-metric and stage-attribution retrieval baseline."
requirement_ids: [P06-59]
---

# Packet 59 — Create a tested, private-safe dual-metric and stage-attribution retrieval baseline.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

Do not load ingestion, FastAPI-router, or frontend skills.

## Preconditions

- P06-58 is recorded. Branch is `fix/general-rag-retrieval-accuracy`.
- Inspect existing evaluation scorers, private-eval scripts, and
  [`docs/evaluation/COMPANY_DOCUMENTS_RAG_100.md`](../../../../../docs/evaluation/COMPANY_DOCUMENTS_RAG_100.md)
  before editing.
- Private gold, credentials, and unrestricted excerpts remain
  gitignored.

## Allowed outputs

- One tested dual-metric scorer module under evaluation or core
  evaluation packages, replacing duplicated scoring logic
- Stage-attribution types for source resolution, dense/BM25/term hit,
  fused rank, rerank rank/fallback, post-MMR rank, coverage
  components, and correction outcome
- Private-safe runner changes: full-answer scoring, a fresh
  conversation per question, no embedded credentials
- Docs correcting the 33 “no evidence” diagnosis and recording the
  live corpus duplicate/title issue without pasting unrestricted PDF
  text
- Packet evidence under `docs/development/phase-06/`
- Tests for strict phrase, approved-alias/semantic fact coverage,
  product-deadline failure counting, and HTML-unescape parity

## Forbidden outputs

- Changing Hybrid retriever ranking, source scope, BM25, term RPCs,
  coverage thresholds, correction routing, or frozen profiles.
- Embedding the sample PDF hash, book title, question IDs, gold
  phrases, expected answers, page numbers, or aliases in production
  modules or committed tests.
- Committing credentials, DSNs, or unrestricted source text.
- Opening holdout or marking P06-17 complete.
- Starting Packet 60 source-resolution coding.

## Ordered actions

1. Replace duplicated scoring helpers with one tested scorer that
   scores the full answer text, unescapes HTML, and reports strict
   phrase and approved-alias/semantic fact coverage separately.
2. Count product-deadline failures as a first-class metric, distinct
   from verifier refusals and wrong answers.
3. Attribute each development sample outcome to retrieval stages:
   source resolution, dense/BM25/term hit, fused rank, rerank
   rank/fallback, post-MMR rank, coverage components, and correction
   outcome.
4. Require a fresh conversation per question in the development
   runner. Remove embedded credentials; load secrets from the existing
   environment contract.
5. Map sample development facts to current canonical chunks with
   human-review placeholders in private files only. Add a separate
   disjoint qualification case schema that committed tests populate
   with synthetic documents, not the sample PDF.
6. Correct the published diagnosis that 33 runs had empty retrieval.
   Record duplicate copies and non-canonical titles as a corpus issue.

## Acceptance checks

- One scorer is imported by runner and rescore paths; duplicated
  scoring logic is gone.
- Unit tests cover strict pass, alias/semantic pass with strict fail,
  deadline fail, verifier refusal after fusion, and unescape parity.
- Committed tests contain no sample-PDF gold, hash, or book title.
- Runner documentation states a fresh conversation per question and
  environment-sourced credentials.
- Evidence records stage buckets without unrestricted excerpts.

## Negative tests

- Scoring only a truncated excerpt while claiming full-answer accuracy
  fails.
- Embedding `mu@admin.com` or a password in a committed runner fails.
- Treating verifier refusal as proven empty retrieval fails.
- Changing retrieval ranking in this packet fails.

## Stop routes

- Stop if private gold cannot be kept out of git.
- Stop if human chunk mapping would require pasting unrestricted PDF
  text into committed docs.
- Do not retune retrieval to chase the baseline scorer in this packet.

## Required evidence

- Packet file under `docs/development/phase-06/` plus index append.
- Commands:

  ```powershell
  uv run python -m pytest tests/unit/test_retrieval_dual_metric_scorer.py -q
  uv run python scripts/check.py --tier docs
  git diff --check
  ```
