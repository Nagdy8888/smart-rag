# P06-24 — PDF eval channel diagnostics (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Authorized per-channel IDs after Supabase recheck on `HybridRunResult`
(`dense_ids`, `bm25_ids`, `term_ids`). Gold-loss stages:
`absent_all_channels`, `channel_not_fused`, `fused_dropped`, `selected`.
CLI prints `gold_loss_histogram` as count-only tokens.

Requirement: do not claim Recall@10 from the 2026-09-10 2/24 ungrounded
labels. `holdout_opened=false`.

Files:

- Additive Hybrid run result fields and `unique_chunk_ids` population
- [`packages/core/src/smart_rag_core/evaluation/private_pdf/metrics.py`](../../../packages/core/src/smart_rag_core/evaluation/private_pdf/metrics.py)
- [`scripts/pdf_eval_runtime.py`](../../../scripts/pdf_eval_runtime.py)
- [`tests/unit/test_pdf_eval_channel_diagnostics.py`](../../../tests/unit/test_pdf_eval_channel_diagnostics.py)
- [`tests/unit/test_hybrid_run.py`](../../../tests/unit/test_hybrid_run.py) (`test_retrieve_records_authorized_channel_ids`)
- [`docs/evaluation/PDF_HYBRID_EVALUATION.md`](../../evaluation/PDF_HYBRID_EVALUATION.md)

Verification:

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_pdf_eval_channel_diagnostics.py tests/unit/test_hybrid_run.py::test_retrieve_records_authorized_channel_ids -q` | 0 |

Proven: synthetic IDs map to the four loss stages; channel IDs are unique
chunk IDs, not BM25 snippets; development tooling still prints
`holdout_opened=false`.

Unverified: live development/qualification histograms. Human reseal remains
the operator blocker before Packet 25 may retune.

Rollback: drop optional channel ID fields; keep prior retrieve scoring.

Handoff: Packet 25 may repair rerank schema/timeout contracts. Freeze stays
denied until grounded live reports exist.
