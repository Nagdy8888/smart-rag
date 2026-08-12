---
title: Workspace and import boundaries
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering
---

# Workspace boundaries

| Distribution | Import | May depend on |
| --- | --- | --- |
| smart-rag-core | smart_rag_core | (none of apps) |
| smart-rag-agents | smart_rag_agents | smart-rag-core |
| smart-rag-backend | smart_rag_api | smart-rag-agents, smart-rag-core |
| smart-rag-worker | smart_rag_worker | smart-rag-agents, smart-rag-core |
| smart-rag-frontend | — | HTTP/Supabase only |

Enforced by `tests/contract/test_import_boundaries.py`. One `uv.lock`, one `pnpm-lock.yaml`, one `apps/agents/langgraph.json`.

[docs index](../README.md)
