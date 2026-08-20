---
title: Graph mapping contract
owner: engineering-lead
status: draft
last-reviewed: 2026-08-20
audience: engineering, reviewers
phase_packet: Phase 5 Packet 4
---

# Graph mapping contract

Canonical identities, exact per-passage LightRAG sources, coverage gates, and
the Graph Ready transaction are specified in [MAPPING.md](./MAPPING.md). This
file is the thin Packet 4 contract pointer so later packets do not duplicate
mapping rules.

Do not treat `lightrag_source_map` alone as evidence. Do not parse rendered
`only_need_context` prose. Do not use vendor `processed` as Graph Ready.
Do not spend Hybrid/rerank mapping calls to paper over LightRAG chunker
mismatch. Source snapshot drift is terminal
`graph_source_snapshot_mismatch`.

The original Graph-200 whole-version attempt measured **87/95** persisted
chunk maps and **2,832/3,314 (85.46%)** coverage, below the 90% gate. The
approved rebuild indexes each canonical Hybrid passage as its own LightRAG
source. Inserts are resumable batches of eight with `AsyncOpenAI` below the
LightRAG watchdog; the 90% / 0.80 gates are unchanged. See
[ADR-canonical-passage-lightrag-sources.md](../adr/ADR-canonical-passage-lightrag-sources.md)
and
[ADR-lightrag-async-embed-batched-sources.md](../adr/ADR-lightrag-async-embed-batched-sources.md).

Query-time resolution, survival, and inspection are specified in
[RETRIEVAL.md](./RETRIEVAL.md). Mapping rows are never citations by themselves.
Entity-rule canonical keys, inactive suggestions, and rebuild scheduling are
specified in [ENTITY_RULES.md](./ENTITY_RULES.md). Production mapping Hybrid
wiring (worker `bind_mapping_support`, in-memory version canonicals, no
query-time Hybrid) is specified in [MAPPING.md](./MAPPING.md).

Related: [LIGHTRAG_CONTRACT.md](./LIGHTRAG_CONTRACT.md) ·
[WORKSPACE_LIFECYCLE.md](./WORKSPACE_LIFECYCLE.md) ·
[ADR-canonical-passage-lightrag-sources.md](../adr/ADR-canonical-passage-lightrag-sources.md) ·
[RETRIEVAL.md](./RETRIEVAL.md) ·
[FROZEN_GRAPH_MANIFEST.md](./FROZEN_GRAPH_MANIFEST.md) ·
[PHASE5_GRAPH_EVAL.md](../evaluation/PHASE5_GRAPH_EVAL.md) ·
[phase-05 evidence](../development/phase-05-graphrag-evidence.md) ·
[docs index](../README.md)
