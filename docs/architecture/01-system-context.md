---
title: C4 — System context
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering
---

# System context

Actors and external systems for Smart RAG. Local topology is current; managed cloud is planned.

```mermaid
flowchart LR
  user["CompanyUser"] --> frontend["NextJsFrontend"]
  frontend --> supabaseAuth["SupabaseAuth"]
  frontend --> api["FastAPI"]
  api --> supabaseDb["SupabasePostgres"]
  api --> parade["PrivateParadeDB"]
  api --> valkeyL["ValkeyLimits"]
  api --> valkeyC["ValkeyCache"]
  api --> openai["OpenAI"]
  api --> langsmith["LangSmithOptional"]
  worker["IngestionWorker"] --> supabaseDb
  worker --> parade
  worker --> crawl["CrawlProxy"]
  crawl --> web["PublicWeb"]
  worker --> openai
  worker --> langsmith
```

## Trust boundaries

- Browser holds only public Supabase config and user JWTs.
- FastAPI verifies JWTs (Phase 2+) and never exposes ParadeDB/Valkey/LightRAG publicly.
- Canonical evidence and security state live in Supabase; ParadeDB is derived BM25 only.
- OpenAI receives bounded evidence only after governance sign-off.
- LangSmith receives redacted run metadata only when `LANGSMITH_TRACING=true`.
  See [LANGSMITH_TRACING.md](../development/LANGSMITH_TRACING.md).

## Links

- [docs index](../README.md)
- [Containers](./02-containers.md)
