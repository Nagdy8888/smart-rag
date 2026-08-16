---
title: C4 — Components
owner: engineering-lead
status: draft
last-reviewed: 2026-08-16
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
  gw --> langsmith["LangSmithRedacted"]
  core --> repos["repositories planned"]
  core --> bm25["Bm25Retriever"]
  core --> dense["DenseRetriever"]
  core --> terms["TermRetriever"]
  core --> tables["structured_table_query"]
  core --> graphR["GraphRetriever planned"]
  core --> tools["optional tool registry"]
```

| Component | Ownership | Phase status |
| --- | --- | --- |
| FastAPI routers/middleware | `apps/backend` | foundation live/ready |
| LangGraph query admission / routing / fusion / optional tools / answer / verifier / ingestion probe | `apps/agents` | query: `enforce_admission` → memory → prepare → plan → branches → one correction → fuse → tables → optional tools → answer → verify; ingestion: lease/ledger probe |
| Worker entrypoint | `apps/worker` | process contract only |
| Settings / logging / model gateway / LangSmith | `packages/core` | Gateway tracing live; production query-graph feedback is Phase 6 |
| Hybrid retrieval / BM25 / LightRAG | `packages/core` | Phase 4 Packet 2–7 dense/BM25/term/rerank/coverage/tables; LightRAG Phase 5 |
| Next.js UI | `apps/frontend` | scaffold; Stitch Phase 8 |

## Links

- [Containers](./02-containers.md)
- [Workspace boundaries](../development/WORKSPACE_BOUNDARIES.md)
- [Hybrid retrieval contract](../retrieval/HYBRID_RETRIEVAL_CONTRACT.md)
- [Structured-table contract](../retrieval/STRUCTURED_TABLE.md)
- [LangSmith tracing](../development/LANGSMITH_TRACING.md)
- [Query routing](../agent/QUERY_ROUTING.md)
- [Combined fusion](../agent/COMBINED_FUSION.md)
- [Answer verification](../agent/ANSWER_VERIFICATION.md)
- [Optional tools](../agent/OPTIONAL_TOOLS.md)
- [docs index](../README.md)
