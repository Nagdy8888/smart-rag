---
title: Query latency repair evidence
owner: engineering-lead
status: draft
last-reviewed: 2026-09-24
audience: engineering, reviewers
---

# Query latency repair evidence

Measured evidence for the query latency repair (packets L0 to L9). Numbers
only: no answer, gold, query, or passage text. How each number is produced
is in [QUERY_LATENCY_REPORT.md](./QUERY_LATENCY_REPORT.md).

Related: [DUAL_METRIC_SCORING.md](./DUAL_METRIC_SCORING.md) ·
[docs index](../README.md)

## Baseline before the repair

Fresh-50 run of 2026-09-23 (50 runs), measured read-only on 2026-09-24
with `eval_latency_report.py report` and
`eval_citation_page_score.py`.

| Metric | Value |
| ------ | ----: |
| `server_total_s` mean | 44.883 s |
| `server_total_s` median | 45.867 s |
| `server_total_s` p90 | 51.909 s |
| `server_total_s` max | 53.204 s |
| Runs with `server_total_s` at most 25 s | 1 |
| Runs with `server_total_s` at most 30 s | 2 |
| `deadline_exhausted` runs | 4 |
| Median `event_spacing_median_s` | 0.532 s |
| Fact plus gold-page citation | 13 |
| Fact plus citation one page away | 2 |
| Fact with citation on another page | 4 |
| Gold page cited | 19 |

Diagnosis notes from the same data: admission to first event median
3.8 s; first event to first stage median 1.8 s; `company_scope` median
14.6 s; rerank sent and then timed out on 44 of 49 rerank calls; a
database round trip from the container is 85 to 95 ms and a new connection
about 500 ms.

## Latency-12 baseline

| Run | `wall_seconds` median | `server_total_s` median | `server_total_s` p90 | `deadline_exhausted` |
| --- | --------------------: | ----------------------: | -------------------: | -------------------: |
| `L0-a` | 44.742 | 38.392 | 42.227 | 0 |
| `L0-b` | 45.602 | 39.325 | 45.148 | 0 |
| Noise band (abs `L0-b` minus `L0-a`) | 0.860 | 0.933 | 2.921 | 0 |

`stage_timings_ms` medians in `L0-b` (milliseconds): assemble_ms=2.0, channel_bm25_ms=983.5, channel_dense_ms=1565.5, channel_term_ms=811.0, channels_ms=1588.5, embed_ms=1357.0, locator_reload_ms=0.0, pool_preload_ms=472.5, rerank_call_ms=8598.5, rerank_gate_remaining_ms=7764.0, retrieve_total_ms=13011.5, scope_ms=917.5, selection_ms=9179.5, temporal_load_ms=640.5.

## Per-packet timing log

| Packet | Before tag | After tag | `wall_seconds` median | `server_total_s` median | `server_total_s` p90 | Targeted metric | Before | After | Noise band | `deadline_exhausted` |
| ------ | ---------- | --------- | --------------------: | ----------------------: | -------------------: | --------------- | -----: | ----: | ---------: | -------------------: |
| L0 | - | `L0-b` | 45.602 | 39.325 | 45.148 | noise band | - | - | 0.860 | 0 |
| L1 | `L0-b` | `L1-after` | pending | pending | pending | `pre_first_stage_s` median | pending | pending | pending | pending |
| L2 | `L1-after` | `L2-after` | pending | pending | pending | parallel `server_total_s` median | pending | pending | pending | pending |
| L3 | `L2-after` | `L3-after` | pending | pending | pending | `node_gap_total_s` median | pending | pending | pending | pending |
| L4 | `L3-after` | `L4-after` | pending | pending | pending | `event_spacing_median_s` median | pending | pending | pending | pending |
| L5 | `L4-after` | `L5-after` | pending | pending | pending | `rerank_timeout_after_send` count | pending | pending | pending | pending |
| L6 | `L5-after` | `L6-after` | pending | pending | pending | `stage_timings_ms.retrieve_total_ms` median | pending | pending | pending | pending |
| L7 | `L6-after` | `L7-after` | pending | pending | pending | answer completion tokens median | pending | pending | pending | pending |
