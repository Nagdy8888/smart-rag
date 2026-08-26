---
title: ADR — Hosted runtime Supabase, local test fixture
adr_id: ADR-hosted-runtime-local-test-fixture
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-25
approver: "user (Cursor chat; hosted chat persistence; keep local only for destructive tests)"
approval_date: "2026-08-25"
audience: engineering, ops, security, reviewers
---

# ADR: Hosted runtime Supabase, local test fixture

## Status

`accepted` — 2026-08-25. The user directed that real chat and application
runtime persist to hosted Supabase, not local Docker Postgres. After
confirming the org is on Free (branching requires Pro) the user kept local
Supabase only for isolated destructive migration/RLS/CI tests.

## Context

Global contracts and P08-22 still described a local-Supabase daily topology.
Laptop Compose defaults interpolated `host.docker.internal:54321/54322`.
Operator overlays already pointed `.env.compose` at hosted Auth/Postgres
([ADR-demo-local-ingest-aws-ask.md](./ADR-demo-local-ingest-aws-ask.md),
[ADR-phase10-hosted-supabase-reuse.md](./ADR-phase10-hosted-supabase-reuse.md)),
but a later process-env overlay flipped API/worker back to local `54322`.
Chat rows then landed on the local fixture while the operator expected
hosted durability.

Supabase Branching (isolated preview databases) requires Pro. The org
already occupies both Free project slots (`smart-rag` healthy, `Reel`
inactive). Destructive schema-reset and RLS suites cannot share the live
application project.

```mermaid
flowchart LR
  browser[BrowserAsk]
  api[LaptopOrEC2API]
  hosted[HostedSupabaseCanonical]
  parade[PrivateParadeDB]
  localFix[LocalSupabaseTestFixture]
  browser --> api
  api --> hosted
  api --> parade
  localFix -.->|"destructive CI only"| hosted
```

## Decision

1. Hosted project `smart-rag` (`qsjivtwtmlmtksufqjik`) is the only runtime
   Auth/Postgres/Storage target for conversations, messages, runs, events,
   citations, budgets, LangGraph checkpoints/store, and LightRAG tables.
2. Local Docker Supabase is a labelled **destructive-test fixture**, not a
   runtime default. `scripts/dev.ps1` must not start or reset it.
3. Private ParadeDB stays a derived BM25 index on laptop/EC2. Never install
   `pg_search` on hosted Postgres.
4. FastAPI short RPC may use the hosted transaction pooler (`:6543`).
   Worker, LangGraph checkpoint/store, and LightRAG require session/direct
   (`:5432` session pooler or equivalent). Never put checkpoints on `:6543`.
5. Destructive contract tests refuse `*.supabase.co` / pooler hostnames.
6. P08-22 live proof is hosted Auth/Postgres plus laptop Compose sidecars
   (ParadeDB, Valkey, crawl-proxy, API, worker, frontend).

## Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| Keep local Supabase as the daily runtime | User required hosted chat persistence |
| Remove local Supabase entirely | Destructive reset/RLS cannot share the live project; branching needs Pro |
| Upgrade to Pro and use ephemeral branches | User chose to keep local tests after the Free-plan limit |
| Use the same hosted project for destructive suites | Data-loss and test-collision risk |

## Consequences

- Compose interpolation fails closed without explicit hosted env names.
- Historical P08-22 “local topology” evidence is a test-fixture record, not
  the current operator path.
- Phase 9 local-release scripts that start CLI Supabase remain fixture
  tools; they are not the product runtime.

## Related

- [ADR-phase10-hosted-supabase-reuse.md](./ADR-phase10-hosted-supabase-reuse.md)
- [ADR-demo-local-ingest-aws-ask.md](./ADR-demo-local-ingest-aws-ask.md)
- [demo-local-ingest-aws-ask.md](../runbooks/demo-local-ingest-aws-ask.md)
- [CONFIGURATION.md](../development/CONFIGURATION.md)
