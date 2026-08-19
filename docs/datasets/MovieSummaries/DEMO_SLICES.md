---
title: Demo plot-summary slices
owner: engineering-lead
status: draft
last-reviewed: 2026-08-19
audience: engineering, ops
---

# Demo plot slices

Do **not** ingest `plot_summaries.txt` (~42,306 lines).

| File | Source lines | Upload as |
| --- | --- | --- |
| `plot_summaries.graph-200.txt` | 1–200 | one `.txt` document; mark graph-eligible after promote |
| `plot_summaries.hybrid-800.txt` | 201–1000 | one `.txt` document; leave graph-ineligible |

Procedure: [demo-local-ingest-aws-ask.md](../../runbooks/demo-local-ingest-aws-ask.md).
Regenerate: `uv run python scripts/ops/cut_plot_summary_demo_slices.py`.
Index: [docs/README.md](../../README.md).
