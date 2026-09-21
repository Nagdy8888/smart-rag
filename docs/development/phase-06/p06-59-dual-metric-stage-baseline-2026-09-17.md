---
title: P06-59 dual-metric and stage-attribution baseline
owner: engineering-lead
status: draft
last-reviewed: 2026-09-17
audience: engineering, reviewers
---

# P06-59 — Dual-metric and stage-attribution baseline (2026-09-17)

Parent index:
[phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement ID: `P06-59`.

## Plan requirement

Quote: create a tested, private-safe dual-metric and stage-attribution
retrieval baseline.

Positive checks: one scorer for runner and rescore; full-answer scoring;
HTML unescape; strict versus alias/semantic fact coverage; deadline
failures distinct from verifier refusals; empty retrieval only when
stages prove it; environment-sourced credentials; fresh conversation per
question; committed tests contain no sample-PDF gold.

Negative checks: no Hybrid ranking, source-scope, BM25, term RPC,
coverage-threshold, or frozen-profile changes; no embedded credentials.

## Files changed

- `packages/core/src/smart_rag_core/evaluation/dual_metric.py`
- `packages/core/src/smart_rag_core/evaluation/company_ask_regression.py`
- `scripts/rescore_company_ask.py`
- `tests/unit/test_retrieval_dual_metric_scorer.py`
- [DUAL_METRIC_SCORING.md](../../evaluation/DUAL_METRIC_SCORING.md)
- [COMPANY_DOCUMENTS_RAG_100.md](../../evaluation/COMPANY_DOCUMENTS_RAG_100.md)
- [PDF_HYBRID_EVALUATION.md](../../evaluation/PDF_HYBRID_EVALUATION.md)

## Verification

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_retrieval_dual_metric_scorer.py tests/contract/test_docstrings.py -q` | 0 (10 passed) |
| `uv run ruff check` on the new Python files | 0 |
| `uv run python scripts/check.py --tier docs` | 0 |
| `git diff --check` | pending |

## Proven

- Duplicated excerpt scoring is replaced by one tested scorer.
- Verifier refusal after fusion is not classified as empty retrieval.
- The 2026-09-17 “33 no evidence” diagnosis is corrected in the public
  report. Strict 37% remains the historical lexical baseline.
- Synthetic disjoint case schema exists without sample-PDF literals.

## Unverified

- Live rescore of the private 100-question gold file. That belongs to
  P06-64 after retrieval repairs.
- Human mapping of sample facts to current canonical chunks stays in
  gitignored files.

## Rollback

Delete the dual-metric module, runner helpers, rescore CLI, and scoring
docs. Restore the prior COMPANY_DOCUMENTS diagnosis. Do not change
retrieval ranking.

## Handoff to P06-60

Implement authorized source resolution, ranking-query title stripping,
and post-ACL exact-duplicate collapse.
