---
title: P06-61 term and BM25 candidate repair
owner: engineering-lead
status: draft
last-reviewed: 2026-09-17
audience: engineering, reviewers
---

# P06-61 — Term and BM25 candidate repair (2026-09-17)

Parent index:
[phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement ID: `P06-61`.

## Plan requirement

Quote: repair term and BM25 candidate generation and selectively enrich
indexed search terms.

Positive checks: term channel receives bounded extracted tokens; extra
needles are bound `text[]` values; ACL/current-version recheck still
drops unauthorized, stale, and deleted IDs; one BM25 variant cannot fill
the unique cap; acronym/mixed-case enrichment is generic; outage records
`term_unavailable` or `bm25_unavailable`.

Negative checks: SQL metacharacters stay data; aliases absent from the
query cannot be injected; tests contain no sample-PDF gold; this packet
does not reindex every live duplicate copy.

## Files changed

- `packages/core/src/smart_rag_core/retrieval/term_needles.py`
- `packages/core/src/smart_rag_core/retrieval/terms.py`
- `packages/core/src/smart_rag_core/retrieval/hybrid_run/channels.py`
- `packages/core/src/smart_rag_core/retrieval/hybrid_run/jobs.py`
- `packages/core/src/smart_rag_core/ingestion/embeddings/contextual.py`
- `supabase/migrations/20260917120000_retrieve_term_candidates_extra_terms_v1.sql`
- `tests/unit/test_term_candidates.py`
- `tests/unit/test_bm25_variant_balance.py`
- `tests/unit/test_search_term_enrichment.py`

## Reindex one canonical test version

Apply the migration, then requeue **one** `hybrid_index` job after a
new canonical persist of that version:

```powershell
uv run python scripts/ops/ingest_private_pdf.py --requeue-hybrid-index <job_id>
```

Do not requeue every duplicate copy in this packet.

## Verification

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_term_candidates.py tests/unit/test_bm25_variant_balance.py tests/unit/test_search_term_enrichment.py -q` | 0 |
| `uv run python scripts/check.py --tier docs` | 0 |
| `git diff --check` | 0 (CRLF warnings only) |

## Proven

- Ranking sentences plus bounded needles reach the term channel.
- Unique BM25/term capping round-robins variants.
- Needle-in-index gaps for parenthetical acronyms and mixed-case tokens
  are filled generically.

## Hosted application (updated 2026-09-21)

Applied on `smart-rag` `qsjivtwtmlmtksufqjik` from commit `d1376ad`
code plus the P06-66 operator apply. Prompt pins `answer_v3` /
`verifier_v2`. Profiles `hybrid_default_v1`
`def45b691e64707d07d3c7ea47f45eb1b23b5d2d2546c37a19a514f316c5940c` and
`hybrid_long_document_v2`
`9565a14152c9c530ad5a07ba221f9d944a872c6b6f417e71ef30cab0486c95b1`.

Hosted `pg_proc` is seven-argument `SECURITY INVOKER` with
`search_path=pg_catalog, app, extensions, search`, `EXECUTE` for
`app_api` only, `functiondef_md5=ad1db6b68caa0ec1236b9c6d5caa6770`.
Three-question Smoke A recorded `term_unavailable=0`.

## Unverified

- Live reindex of one canonical test version (P06-67).

## Rollback

Drop the 7-argument `retrieve_term_candidates` and restore the 6-argument
function from `20260814130000_hybrid_retrieval_v1.sql`. Restore first-seen
variant capping and the previous search-term extractor.

## Handoff to P06-62

Repair retrieve-time durable call accounting and qualify a measured
immutable long-document profile.
