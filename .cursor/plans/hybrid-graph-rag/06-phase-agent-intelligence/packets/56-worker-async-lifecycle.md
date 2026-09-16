---
phase: 6
packet: 56
status: pending
title: "Use the approved local host-worker parser topology and prove sequential Exa runs without cross-loop cleanup errors."
requirement_ids: [P06-56]
---

# Packet 56 — Use the approved local host-worker parser topology and prove sequential Exa runs without cross-loop cleanup errors.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-ingestion-pipeline`](../../../../../.cursor/skills/implement-ingestion-pipeline/SKILL.md),
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

## Preconditions

- P06-55 is recorded. Branch is `fix/rag-reliability-and-citations`.
- Approved local pattern is
  `scripts/ops/run_laptop_ingest_worker.py`. Inspect Compose worker
  service, `dev.ps1`, `stop.ps1`, `verify-local.ps1`, and
  `ExaSearchGateway` before editing.

## Allowed outputs

- `docker-compose.yml` worker profile only (no raw socket)
- `docker-compose.packet8.yml` host-only published ports
- `scripts/dev.ps1`, `scripts/stop.ps1`, `scripts/verify-local.ps1`
- `scripts/ops/run_laptop_ingest_worker.py` if metadata/PID contract
  requires it
- `packages/core/src/smart_rag_core/gateways/exa_search.py`
- `apps/agents/src/smart_rag_agents/query/runtime/deps_factory.py`
- Related query runtime adapters already owning Exa lifecycle
- Tests listed below
- `docs/ingestion/PARSER_SANDBOX.md`, Compose topology docs, local
  runbook, and packet evidence

## Forbidden outputs

- Granting the worker the raw Docker socket.
- In-process parsing on staging/production.
- Suppressing `Event loop is closed` warnings.
- Closing a process-shared Exa gateway behind another in-flight run.
- Changing production/EC2 parser topology.
- Hard-coded public DNS servers.
- Starting Packet 57 live qualification before these tests pass.

## Ordered actions

1. Put the incompatible distroless Compose `worker` behind an explicit
   non-default profile so the default stack excludes it.
2. `dev.ps1` validates gitignored `.env.compose` names without
   printing values, builds the parser image with profile
   `parser-build`, starts `paradedb`, both Valkeys, `clamav`,
   `crawl-proxy`, `api`, and `frontend` via base plus packet8, binds
   packet8 ports to `127.0.0.1:54329`, `127.0.0.1:13310`, and
   `127.0.0.1:18080`, then launches the host worker with gitignored
   logs and PID/start-time metadata.
3. `stop.ps1` stops that PID only after command line and start time
   match this repository launcher. Missing/stale/mismatched PIDs are
   reported and left untouched.
4. `verify-local.ps1` fails if the host worker is absent, the parser
   image is missing, or logs contain `parser_sandbox_docker_required`.
   It must not `docker compose exec worker`.
5. Preserve parser `--network none`, non-root/read-only, no secrets.
6. `ExaSearchGateway` opens a fresh `httpx.AsyncClient` inside each
   request attempt and closes it in the same coroutine/loop.
   `aclose()` exposes read-only `closed`. `refresh_web_search_deps`
   recreates a missing, wrong-type, closed, or settings-changed
   gateway.

## Acceptance checks

- Default stack excludes the incompatible worker. Raw socket absent.
- Parser has no egress. Host overlay binds loopback only.
- Scripts use the approved host launcher. Unrelated PIDs are not
  killed.
- Two sequential Web runs succeed. Closed gateway is replaced.
- Create/request/close share one event-loop identity. Zero unhandled
  task exceptions.

## Negative tests

- Mounting `/var/run/docker.sock` fails the packet.
- Killing an unrelated reused PID fails.
- Reusing a closed Exa client across loops fails.

## Stop routes

- Stop rather than weaken isolation if the host-worker flow cannot be
  made reliable without a raw socket or in-process parsing.
- Do not start Packet 57 until Compose config and Exa tests pass.

## Required evidence

- Parser/worker/Exa tests and Compose config. One start/stop of the
  local stack with no restart loop.
- Commands:

  ```powershell
  uv run python -m pytest tests/unit/test_exa_search_gateway.py tests/unit/test_web_research_graph.py tests/unit/test_query_graph_deps.py tests/unit/test_worker_lease_heartbeat.py tests/unit/test_parser_sandbox.py tests/contract/test_parser_sandbox.py tests/contract/test_compose_topology.py -q
  uv run ruff check packages/core/src/smart_rag_core/gateways/exa_search.py apps/agents/src/smart_rag_agents/query apps/worker/src scripts/ops/run_laptop_ingest_worker.py tests/unit/test_exa_search_gateway.py tests/unit/test_web_research_graph.py tests/unit/test_query_graph_deps.py
  uv run pyright packages/core/src/smart_rag_core/gateways/exa_search.py apps/agents/src/smart_rag_agents/query apps/worker/src scripts/ops/run_laptop_ingest_worker.py
  docker compose --env-file .env.example config --quiet
  git diff --check
  ```

- Commit `fix(runtime): align local worker and gateway lifecycles`.
