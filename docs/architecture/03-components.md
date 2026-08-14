---
title: C4 — Components
owner: engineering-lead
status: draft
last-reviewed: 2026-08-14
audience: engineering
---

# Components

```mermaid
flowchart LR
  routers["backend routers"] --> services["backend services"]
  services --> graphs["agents LangGraph"]
  services --> core["smart_rag_core"]
  worker["worker lifecycle"] --> graphs
  worker --> core
  core --> gw["ModelGateway"]
  core --> repos["repositories planned"]
  core --> bm25["Bm25Retriever"]
  core --> dense["DenseRetriever"]
  core --> terms["TermRetriever"]
  core --> graphR["GraphRetriever planned"]
```

| Component | Ownership | Phase status |
| --- | --- | --- |
| FastAPI routers/middleware | `apps/backend` | foundation live/ready |
| LangGraph query/ingestion scaffolds | `apps/agents` | loadable, unconfigured business |
| Worker entrypoint | `apps/worker` | process contract only |
| Settings / logging / model gateway | `packages/core` | Phase 1 Packet 4 |
| Hybrid retrieval / BM25 / LightRAG | `packages/core` | Phase 4 Packet 2 dense/BM25/term adapters; LightRAG Phase 5 |
| Next.js UI | `apps/frontend` | scaffold; Stitch Phase 8 |

## Links

- [Containers](./02-containers.md)
- [Workspace boundaries](../development/WORKSPACE_BOUNDARIES.md)
- [Hybrid retrieval contract](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md)
- [docs index](../README.md)
