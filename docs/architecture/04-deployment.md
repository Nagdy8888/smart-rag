---
title: C4 — Deployment views
owner: engineering-lead
status: draft
last-reviewed: 2026-08-17
audience: engineering, operations
---

# Deployment

## Local (current)

| Node | Port / exposure | State |
| --- | --- | --- |
| Next.js | host 3000 | scaffold |
| FastAPI | host 8000 | live + unconfigured ready |
| Worker | private + edge, no host port | local candidate; `host.docker.internal` for Supabase |
| ParadeDB | private only | pg_search health |
| Valkey limits/cache | private only | auth + distinct policies |
| Crawl proxy | private only | deny-by-default |
| Supabase CLI | 54321+ when installed | stock Phase 1 config |

Start: `.\scripts\dev.ps1` · Stop: `.\scripts\stop.ps1` · Reset: `.\scripts\reset.ps1 -ConfirmReset` · Candidate freeze: [LOCAL_RELEASE_CANDIDATE.md](../deployment/LOCAL_RELEASE_CANDIDATE.md)

## Staging / production (planned)

```mermaid
flowchart LR
  vercel["Vercel"] --> cf["CloudFront WAF"]
  cf --> ec2["EC2 Compose"]
  vercel --> supabase["ManagedSupabase"]
  ec2 --> supabase
  ec2 --> parade["PrivateParadeDB"]
  ec2 --> openai["OpenAI"]
```

## Links

- [Containers](./02-containers.md)
- [Availability triggers](./AVAILABILITY_AND_ISOLATION_TRIGGERS.md)
- [docs index](../README.md)
