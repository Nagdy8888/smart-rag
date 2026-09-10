---
title: PDF Hybrid evaluation
owner: engineering-lead
status: draft
last-reviewed: 2026-09-10
audience: engineering, reviewers
---

# PDF Hybrid evaluation

Private evaluation of one `real_company` PDF. This is not generalization to
other documents, graph questions, or unrestricted full-book summaries.

Related: [hybrid-pdf-accuracy-remediation.md](../development/hybrid-pdf-accuracy-remediation.md) ·
[PHASE4_RANKED_IDS.md](./PHASE4_RANKED_IDS.md) ·
[ADR-hybrid-long-document-profile.md](../adr/ADR-hybrid-long-document-profile.md) ·
[ADR-local-pdf-evaluation-workspace.md](../adr/ADR-local-pdf-evaluation-workspace.md) ·
[PDF_EVAL_WORKSPACE.md](./PDF_EVAL_WORKSPACE.md) ·
[PARSER_BAKEOFF.md](./PARSER_BAKEOFF.md) ·
[docs index](../README.md)

```mermaid
flowchart LR
  ingest["Graph-disabled ingest"] --> seal["Human-sealed labels"]
  seal --> retrieve["Hybrid retrieve"]
  retrieve --> qualify["Qualification once"]
  qualify --> holdout["One immutable holdout"]
```

## Current gates (2026-09-10)

| Gate | Status |
| --- | --- |
| Provider matrix named/date approval | **accepted 2026-09-09** — public defaults; ZDR not claimed |
| Human glossary approve | hash-only draft then owner/admin import |
| Live PDF ingest | **accepted 2026-09-09** — `graph_ineligible`; Graph off |
| Human eval seal | **locator-bound owner seal 2026-09-09**; `holdout_opened=false` |
| Live full-Hybrid development | **no_go 2026-09-10** — BM25 `none`; Recall@10 and locator miss |
| Frozen `hybrid_long_document_v1` runtime allow-list | **denied** — qualification not run |
| Holdout | sealed outside the worktree; not opened |

Locator-bound owner seal (`reviewer=Nagdy`) split 40 open / 20 holdout.
Count-only gold overlap on development (`--probe-gold`): 28 cases, 28
unique gold IDs, 640 representatives, intersection 28, 1 gold ID per
case, `cases_missing_all_representatives=0`. Stale-ID mismatch is not the
Recall@10 miss.

`--probe-grounding` on the same development split: 24 scored non-refusal
cases, **2** whose required terms appear in gold text/heading, 4 refusals,
0 missing gold text. Heading-boilerplate overlap is not grounding. The
first failing stage is label/question alignment, not RRF. The draft
builder now uses only glossary aliases that appear in the gold locator;
unsupported aliases are not cycled onto unrelated passages. A named human
must re-seal before another freeze attempt. The coding model is not
the reviewer.

`scripts/eval_pdf_hybrid.py --split development --live` on candidate
`hybrid_long_document_v1` digest
`d9e154747a88a94c0c75e87935a1f977e1c1802e2e80f9e12825bd24e1d15d22`
(version-scoped exact dense; 8s slice starts after embedding; default pin
unchanged
`def45b691e64707d07d3c7ea47f45eb1b23b5d2d2546c37a19a514f316c5940c`):

| Token | Value |
| --- | --- |
| `case_count` | 28 |
| `fallback_histogram` | `{none: 28}` |
| `dense_term_degraded_count` | 0 |
| `hybrid_recall_at_10` | 0.0417 |
| `fused_occupancy_at_10` | 0.0417 (not the Recall@10 gate) |
| `locator_correctness` | 0.0357 |
| `first_evidence_p95_ms` | 3236 |
| `eligible_rerank_ones` | 7 / 24 |
| `rerank_fallback_histogram` | `{rerank_timeout: 18, none: 7, rerank_schema_invalid: 3}` |
| `gates_pass` | false |
| `holdout_opened` | false |

Rejected candidate hashes (JSON bytes never rewritten in place after a
failed development run; a new digest is a new candidate):

- `ac42dec12e79681badcc382b16312108d6a265d35b1d5b1f962d4ec5e3930109`
  (2026-09-09; ANN; eligible rerank 0/24; p95 10545 ms)
- `d9e154747a88a94c0c75e87935a1f977e1c1802e2e80f9e12825bd24e1d15d22`
  (2026-09-10; version-scoped exact; eligible rerank 7/24; p95 3236 ms)

Identity comparison (`--rerank identity`) on the same split: Recall@10
0.0417, fused occupancy 0.0417, eligible rerank 0/24, `live_rerank=false`.
Live rerank is not the Recall@10 bottleneck. Identity cannot freeze.

Repair 2 (2026-09-10): eval retrieve binds production
`profile_query_sync`. Identity re-run: Recall@10 0.0417,
`gold_in_fused_any` 0.0417, `fused_gold_rank_p50` 9, p95 3955 ms,
`bm25_fallback=none`. Gold is absent from the fused list, not only
top-10. Two real-integration repairs are exhausted. Stop. Do not freeze,
open holdout, or edit the failed digest.

`--fault paradedb` against an unreachable writer URL: `bm25_fallback=retrieval_timeout`,
`dense_term_degraded=true`, `full_hybrid=false`. Unit tests still prove the
immediate `bm25_unavailable` path. Degraded rows are not merged into
full-Hybrid metrics.

The 8s retrieve slice was not raised. First-evidence is stamped when fused
IDs exist, before rerank. `hybrid_long_document_v1` is not frozen.
Qualification was not run.

The coding model is not a row-by-row PDF gold adjudicator. Do not claim
Recall@10 from fused occupancy. Do not open holdout.

ParadeDB `pg_search` 0.25.2 rejects `version_id` in the same `WHERE` as
`pdb.score` (`XX000` unsupported query shape). Variant BM25 still scopes
with a btree id list and `chunk_id = ANY(...)` on the BM25 key field.

## Production rerank

`ProcessHybridRetriever` now binds `rerank_pool` and `rerank_v1` under
`hybrid_default_v1`. Identity output cannot satisfy the live-rerank gate.
Unfrozen `hybrid_long_document_v1` stays rejected by `load_frozen_profile()`.

`HybridRunResult.ranked_ids` is the post-rerank/MMR/parent/trim order.
`fused_ids` preserves historical fused occupancy for synthetic compact-corpus
comparisons. Overlay Packet 24 adds authorized `dense_ids`, `bm25_ids`, and
`term_ids` after recheck. CLI reports print `gold_loss_histogram` as
count-only tokens. BM25 snippets are never diagnostics.

## Overlay freeze, Combined, and holdout (2026-09-10)

| Gate | Status |
| --- | --- |
| PDF heading extraction | `parser_v1_pdf_headings_v1` unit-proven; live reingest operator-owned |
| Human reseal | operator-owned; labels remain 2/24 grounded |
| `FROZEN_LONG_DOCUMENT_PROFILE_SHA256` | empty; `runtime_allow_listed=false` |
| Invalid JSON rerank | typed `rerank_schema_invalid` → RRF fallback |
| Retrieval cache | ID/rank only; recheck on hit; outage is a miss |
| `qt_eval_009_status` | `unverified` (no disjoint graph-eligible live set) |
| `holdout_opened` | `false` |

Do not retune from the 2026-09-10 2/24 ungrounded baseline. Do not freeze
`hybrid_long_document_v1` without live development and qualification reports.

## Verification

```text
uv run python scripts/draft_pdf_eval_dataset.py
uv run python scripts/seal_pdf_eval_dataset.py --input .private-eval/<pdf-sha12>/v1/draft.json
uv run python scripts/eval_pdf_hybrid.py --probe-gold
uv run python scripts/eval_pdf_hybrid.py --probe-grounding
uv run python scripts/eval_pdf_hybrid.py --split development --live
uv run python scripts/eval_pdf_hybrid.py --split development --live --rerank identity
uv run python scripts/eval_pdf_hybrid.py --fault paradedb
uv run python scripts/eval_pdf_agent.py --split development
uv run python scripts/eval_pdf_holdout.py --labels .private-eval/holdout/labels.json
```

Draft writes counts and hashes only. Seal of generated-only rows exits `2`.
Live development Hybrid on 2026-09-10 ran after a named locator-bound seal
and reported `gates_pass=false` after two retrieve repairs. Qualification,
freeze, agent eval, and holdout stay closed. They never open holdout.
