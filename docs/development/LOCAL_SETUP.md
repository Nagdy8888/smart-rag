---
title: Local setup
owner: engineering-lead
status: draft
last-reviewed: 2026-09-16
audience: engineering
---

# Local setup

Daily laptop runtime uses hosted Supabase plus Compose sidecars. See
[ADR-cloud-only-supabase-no-local-fixture.md](../adr/ADR-cloud-only-supabase-no-local-fixture.md).

```mermaid
flowchart LR
  browser[Browser]
  compose[LaptopCompose]
  hosted[HostedSupabase]
  parade[PrivateParadeDB]
  browser --> compose
  compose --> hosted
  compose --> parade
```

1. Install Docker Desktop (WSL2), uv, Node 20+, and pnpm 9.15+.
2. Run `uv sync --all-packages --group dev --python 3.11 --frozen`.
3. Run `pnpm install --frozen-lockfile`.
4. Put hosted session/transaction URLs in ignored `.env`, then run
   `uv run python scripts/ops/wire_hosted_ingest_env.py`. That writes
   `SUPABASE_URL`, `API_SUPABASE_DB_URL`, `WORKER_SUPABASE_DB_URL`,
   `LANGGRAPH_CHECKPOINT_URL`, and `LIGHTRAG_DB_URL` into `.env.compose`
   without printing secrets. Also set `NEXT_PUBLIC_SUPABASE_URL` and
   `NEXT_PUBLIC_SUPABASE_ANON_KEY` before building the frontend image.
5. Run `.\scripts\dev.ps1`. It validates `.env.compose` names without
   printing values, builds `smart-rag-parser-sandbox:local` with profile
   `parser-build`, starts ParadeDB, both Valkeys, ClamAV, crawl-proxy,
   api, and frontend via base plus packet8 loopback binds, then launches
   `scripts/ops/run_laptop_ingest_worker.py` with gitignored logs and
   PID/start-time metadata. It does not start the distroless Compose
   `worker`. Then run `.\scripts\verify-local.ps1`. `.\scripts\stop.ps1`
   stops that host PID only when command line and start time match this
   launcher.
   Do not leave a loopback `SUPABASE_URL` in `.env` while Compose is running.
   That value wins interpolation over `.env.compose`, so Ask returns 401
   `unauthorized` after a hosted sign-in.
   If Ask says `query_ready` is false while Valkey is healthy, a single
   limits timeout latched `rate_limit_degraded`. Restart the API to clear
   it immediately. After this change, `/health/ready` clears the latch
   when both Valkey probes are `ok`.
6. Destructive RLS/schema suites are opt-in against an explicit non-hosted
   `SUPABASE_DB_URL`. They refuse `*.supabase.co`.
7. To inspect the query graph in LangGraph Studio (unbound, no FastAPI
   admit), run `.\scripts\langgraph-studio.ps1` and open the printed Studio
   URL. Select `query_studio`. See [LANGGRAPH_STUDIO.md](./LANGGRAPH_STUDIO.md).

`dev.ps1` fails closed without hosted `.env.compose`. `stop.ps1` stops
the matching host ingest worker PID, then Compose. Unrelated PIDs are
left untouched.

The optional PDF evaluation workspace (`PDF_EVAL_WORKSPACE_ENABLED`,
local Compose default `true`) uses hosted quiz RPCs through `app_api`.
When the flag is true and `SUPABASE_DB_URL` is set, the API lifespan starts
one exam supervisor. SQL claim/heartbeat remains durable authority; HTTP
start/poll is Packet 32. The API container is read-only. `.private-eval/`
remains the CLI/legacy file store only; HTTP does not fall back to it.
Staging and production reject the flag. See
[PDF_EVAL_WORKSPACE.md](../evaluation/PDF_EVAL_WORKSPACE.md)
and [ADR-hosted-webapp-evaluation-workspace.md](../adr/ADR-hosted-webapp-evaluation-workspace.md).

See [CONFIGURATION.md](./CONFIGURATION.md), [TOOL_VERSIONS.md](./TOOL_VERSIONS.md),
[LANGGRAPH_STUDIO.md](./LANGGRAPH_STUDIO.md),
[demo-local-ingest-aws-ask.md](../runbooks/demo-local-ingest-aws-ask.md)
(hosted-Supabase laptop ingest uses [`.env.hosted-ingest.example`](../../.env.hosted-ingest.example)),
[docs index](../README.md).
