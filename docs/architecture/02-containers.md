---
title: C4 — Containers
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering
---

# Containers

## Local (current)

```mermaid
flowchart TB
  subgraph edge ["edge network"]
    fe["frontend:3000"]
    api["api:8000"]
  end
  subgraph private ["private internal network"]
    pdb["paradedb no host port"]
    vl["valkey-limits"]
    vc["valkey-cache"]
    cp["crawl-proxy"]
    worker["worker"]
  end
  fe --> api
  api --> pdb
  api --> vl
  api --> vc
  worker --> pdb
  worker --> cp
```

Published developer ports only: frontend and API. ParadeDB, both Valkey instances, and crawl-proxy have **no host ports**.

## Staging / production (planned)

Vercel frontend, CloudFront/WAF → EC2 Compose (API blue/green, worker, ParadeDB, Valkey, crawl proxy), managed Supabase, SES. See Phase 10–11.

## Links

- [System context](./01-system-context.md)
- [Deployment](./04-deployment.md)
- [docs index](../README.md)
