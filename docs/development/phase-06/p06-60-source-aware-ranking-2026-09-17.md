---
title: P06-60 source-aware ranking and post-ACL duplicate collapse
owner: engineering-lead
status: draft
last-reviewed: 2026-09-17
audience: engineering, reviewers
---

# P06-60 — Source-aware ranking and post-ACL duplicate collapse (2026-09-17)

Parent index:
[phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement ID: `P06-60`.

## Plan requirement

Quote: implement authorized source resolution, ranking-query title
stripping, and post-ACL duplicate collapse.

Positive checks: exact authorized title match scopes retrieve; ranking
query drops matched title tokens; ambiguous and unauthorized titles stay
unscoped and indistinguishable; exact duplicate citation text collapses
after ACL recheck; documents remain stored; ingest preserves the upload
filename as the document title.

Negative checks: confidence below 0.80 does not scope; unauthorized
ILIKE cannot scope because ACL omits those rows; collapse never runs on
text that failed ACL recheck; no automatic document deletion; no
sample-PDF gold in production or tests.

## Files changed

- `packages/core/src/smart_rag_core/retrieval/source_scope.py`
- `packages/core/src/smart_rag_core/query_routing/preparation.py`
- `packages/core/src/smart_rag_core/retrieval/rerank.py`
- `apps/agents/src/smart_rag_agents/query/runtime/adapters_hybrid.py`
- `scripts/ops/ingest_private_pdf.py`
- `tests/unit/test_source_scope.py`
- `tests/unit/test_source_aware_ranking.py`
- [HYBRID_RETRIEVAL_CONTRACT.md](../../retrieval/HYBRID_RETRIEVAL_CONTRACT.md)

## Verification

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_source_scope.py tests/unit/test_source_aware_ranking.py tests/contract/test_docstrings.py -q` | 0 |
| `uv run ruff check` on the changed Python files | 0 |
| `uv run python scripts/check.py --tier docs` | 0 |
| `git diff --check` | 0 (CRLF warnings only) |

## Proven

- Exact-one authorized titles become a version scope and selector list.
- Ranking retrieve uses the stripped query and stripped variants.
- Ambiguous and empty authorized matches stay unscoped.
- Exact duplicate copies cannot consume independent document quotas.
- Unauthorized chunks missing from ACL context never enter the pool.

## Unverified

- Live title resolution against the current duplicate PDF copies.
- Whether ingest of new files with original filenames is sufficient to
  scope the sample corpus without a re-finalize of existing rows.

## Rollback

Restore the previous source-scope ILIKE-only matcher, adapter retrieve
query, and rerank pool construction. Existing documents are unchanged.

## Handoff to P06-61

Repair term and BM25 candidate generation and selectively enrich
indexed search terms.
