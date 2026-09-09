---
title: PDF Hybrid evaluation
owner: engineering-lead
status: draft
last-reviewed: 2026-09-09
audience: engineering, reviewers
---

# PDF Hybrid evaluation

Private evaluation of one `real_company` PDF. This is not generalization to
other documents, graph questions, or unrestricted full-book summaries.

Related: [hybrid-pdf-accuracy-remediation.md](../development/hybrid-pdf-accuracy-remediation.md) ·
[PHASE4_RANKED_IDS.md](./PHASE4_RANKED_IDS.md) ·
[ADR-hybrid-long-document-profile.md](../adr/ADR-hybrid-long-document-profile.md) ·
[docs index](../README.md)

```mermaid
flowchart LR
  ingest["Graph-disabled ingest"] --> seal["Human-sealed labels"]
  seal --> retrieve["Hybrid retrieve"]
  retrieve --> qualify["Qualification once"]
  qualify --> holdout["One immutable holdout"]
```

## Current gates (2026-09-09)

| Gate | Status |
| --- | --- |
| Provider matrix named/date approval | **accepted 2026-09-09** — public defaults; ZDR not claimed |
| Human glossary approve | hash-only draft then owner/admin import |
| Live PDF ingest | **accepted 2026-09-09** — `graph_ineligible`; Graph off |
| Human eval seal | **locator-bound owner seal 2026-09-09**; `holdout_opened=false` |
| Live full-Hybrid development | **no_go 2026-09-09** — BM25 `none`; gates miss |
| Frozen `hybrid_long_document_v1` runtime allow-list | **denied** — qualification not run |
| Holdout | sealed outside the worktree; not opened |

Locator-bound owner seal (`reviewer=Nagdy`) split 40 open / 20 holdout.
`scripts/eval_pdf_hybrid.py --split development --live` on candidate
`hybrid_long_document_v1` digest
`ac42dec12e79681badcc382b16312108d6a265d35b1d5b1f962d4ec5e3930109`
(default pin unchanged
`def45b691e64707d07d3c7ea47f45eb1b23b5d2d2546c37a19a514f316c5940c`):

| Token | Value |
| --- | --- |
| `case_count` | 28 |
| `fallback_histogram` | `{none: 28}` |
| `dense_term_degraded_count` | 0 |
| `hybrid_recall_at_10` | 0.0417 |
| `locator_correctness` | 0.0357 |
| `first_evidence_p95_ms` | 10545 |
| `eligible_rerank_ones` | 0 / 24 |
| `gates_pass` | false |
| `holdout_opened` | false |

A dummy Hybrid retrieve after the BM25 repair returned `rerank_fallback=rerank_timeout`
with `deadline_exhausted=false`. Live embedding plus hosted dense (~2.5s for 640
authorized rows) consume the 8s retrieve slice; the one-shot reranker is
attempted then times out. First-evidence p95 is above the 2s gate. The 8s
slice was not raised. `hybrid_long_document_v1` is not frozen.

ParadeDB `pg_search` 0.25.2 rejects `version_id` in the same `WHERE` as
`pdb.score` (`XX000` unsupported query shape). Variant BM25 now scopes with a
btree id list and `chunk_id = ANY(...)` on the BM25 key field.

The coding model is not a row-by-row PDF gold adjudicator. Do not claim
Recall@10 from fused occupancy. Do not open holdout.

## Production rerank

`ProcessHybridRetriever` now binds `rerank_pool` and `rerank_v1` under
`hybrid_default_v1`. Identity output cannot satisfy the live-rerank gate.
Unfrozen `hybrid_long_document_v1` stays rejected by `load_frozen_profile()`.

`HybridRunResult.ranked_ids` is the post-rerank/MMR/parent/trim order.
`fused_ids` preserves historical fused occupancy for synthetic compact-corpus
comparisons.

## Verification

```text
uv run python scripts/draft_pdf_eval_dataset.py
uv run python scripts/seal_pdf_eval_dataset.py --input .private-eval/<pdf-sha12>/v1/draft.json
uv run python scripts/eval_pdf_hybrid.py --split development --live
uv run python scripts/eval_pdf_agent.py --split development
uv run python scripts/eval_pdf_holdout.py --labels .private-eval/holdout/labels.json
```

Draft writes counts and hashes only. Seal of generated-only rows exits `2`.
Live development Hybrid on 2026-09-09 ran after a named locator-bound seal
and reported `gates_pass=false`. Qualification, freeze, agent eval, and
holdout stay closed. They never open holdout.
