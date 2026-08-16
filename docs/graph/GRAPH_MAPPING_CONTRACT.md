---
title: Graph mapping contract
owner: engineering-lead
status: draft
last-reviewed: 2026-08-16
audience: engineering, reviewers
phase_packet: Phase 5 Packet 4
---

# Graph mapping contract

Canonical identities, one-shot Hybrid/rerank, coverage gates, and the Graph
Ready transaction are specified in [MAPPING.md](./MAPPING.md). This file is
the thin Packet 4 contract pointer so later packets do not duplicate mapping
rules.

Do not treat `lightrag_source_map` alone as evidence. Do not parse rendered
`only_need_context` prose. Do not use vendor `processed` as Graph Ready.

Query-time resolution, survival, and inspection are specified in
[RETRIEVAL.md](./RETRIEVAL.md). Mapping rows are never citations by themselves.
Entity-rule canonical keys, inactive suggestions, and rebuild scheduling are
specified in [ENTITY_RULES.md](./ENTITY_RULES.md).

Related: [LIGHTRAG_CONTRACT.md](./LIGHTRAG_CONTRACT.md) ·
[WORKSPACE_LIFECYCLE.md](./WORKSPACE_LIFECYCLE.md) ·
[RETRIEVAL.md](./RETRIEVAL.md) ·
[FROZEN_GRAPH_MANIFEST.md](./FROZEN_GRAPH_MANIFEST.md) ·
[PHASE5_GRAPH_EVAL.md](../evaluation/PHASE5_GRAPH_EVAL.md) ·
[phase-05 evidence](../development/phase-05-graphrag-evidence.md) ·
[docs index](../README.md)
