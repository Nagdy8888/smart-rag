---
title: Database connections and pool budgets
owner: engineering-lead
status: proven
last-reviewed: 2026-09-15
audience: engineering, ops
phase_packet: Phase 2 Packet 6
---

# Database connections and pool budgets

Packet 6 proves worst-case Supabase connections stay below **70%** of the selected
tier hard limit using the **actual** Compose process inventory (not planned
replicas). Canonical Auth/Postgres is the cloud project; see
[ADR-cloud-only-supabase-no-local-fixture.md](../adr/ADR-cloud-only-supabase-no-local-fixture.md).

## Selected tier (managed smart-rag Free/Nano-class)

| Setting | Proven value |
| --- | --- |
| Selected tier hard limit | **60** direct connections |
| 70% budget ceiling | **42** connections |
| Reserved operations | **2** |
| Worst-case provisional sum | **30** |
| Gate | **30 < 42** ✓ |

Managed custody of pooler wiring and production pool changes remains
**Phase 10**; this packet proves local role settings + documented math
against the selected Nano limit. Managed Pro pooling is **Not Run**.
Local worst-case math remains **30 < 42**.

## Process inventory (from `docker-compose.yml`)

| Compose service | Replicas | Publishes host ports | Supabase consumers |
| --- | --- | --- | --- |
| `api` | 1 (no `deploy.replicas`) | yes (`API_HOST_PORT`) | txn + session/direct pools |
| `worker` | 1 | no | txn + LightRAG session |
| `paradedb` | 1 | **none** (private network only) | independent BM25 budget |
| `valkey-limits` | 1 | no | none (Valkey) |
| `valkey-cache` | 1 | no | none (Valkey) |
| `crawl-proxy` | 1 | no (expose 8080 internal) | none |
| `frontend` | 1 | yes | Auth/Storage via Supabase URL only |

```mermaid
flowchart TB
  subgraph compose [docker-compose smart-rag]
    api["api x1"]
    worker["worker x1"]
    frontend["frontend x1"]
    paradedb["paradedb x1\nno host ports"]
    valkeyL["valkey-limits x1"]
    valkeyC["valkey-cache x1"]
    crawl["crawl-proxy x1"]
  end
  subgraph supabaseBudget [Supabase hard limit 60 / ceiling 42]
    txn["Transaction\nAPI 10 + Worker 6"]
    sess["Session/direct\nCheckpointer 4 + LightRAG 4+4"]
    ops["Operations 2"]
  end
  api --> txn
  api --> sess
  worker --> txn
  worker --> sess
  migrate["Migration / ops"] --> ops
  api --> paradedb
  worker --> paradedb
  frontend -.->|JWT Auth only| supabaseBudget
```

**Multiplication:** with one API and one worker process, provisional caps are used
as-is. Adding API/worker replicas would multiply txn/session pools and must
re-run this gate (ADR + resize if ≥42).

## Per-service pool caps (proven candidates)

| Service | Pool mode | Cap | Role |
| --- | --- | --- | --- |
| FastAPI request/RPC | transaction (Supavisor) | 10 | `app_api` |
| FastAPI checkpointer | session/direct | 4 | `app_checkpointer` |
| FastAPI LightRAG adapter | session/direct | 4 | `app_lightrag` |
| Worker ingestion/index | transaction | 6 | `app_worker` |
| Worker LightRAG adapter | session/direct | 4 | `app_lightrag` |
| Operations/migrations | direct | 2 | bootstrap / ops (not runtime) |

**Worst-case sum:** 10 + 4 + 4 + 6 + 4 + 2 = **30** (< 42).

Transaction pooling must not carry session GUC identity; checkpointer and
LightRAG never use transaction mode. `app.validate_caller_context` takes typed
arguments only (contract: `tests/contract/test_connection_budgets.py`).

## Prepared statements on the transaction pooler

Supavisor transaction mode (port `6543`) reuses backend sessions across
clients. Psycopg 3 names prepared statements by default; a later checkout
then raises `DuplicatePreparedStatement` during Hybrid retrieve, citation
persist, or conversation RPC.

Runtime rule: every FastAPI/query `psycopg.connect` that may use
`API_SUPABASE_DB_URL` / `SUPABASE_DB_URL` must go through
`smart_rag_core.settings.postgres_connect.connect_postgres`, which sets
`prepare_threshold=None`. SSE event-store and LangGraph checkpointer already
disable prepares (`prepare_threshold=None` / `0`). asyncpg LightRAG uses
`statement_cache_size=0`. Do not add named prepares on pooler DSNs.

```mermaid
flowchart LR
  api["FastAPI / query retrieve"] --> helper["connect_postgres\nprepare_threshold=None"]
  helper --> pooler["Supavisor txn 6543"]
  sse["SSE event store"] --> pooler
  checkpointer["LangGraph checkpointer"] --> session["Session/direct 5432"]
```

Verification: `uv run pytest tests/unit/test_postgres_dsn.py tests/unit/test_hybrid_run.py tests/unit/test_general_chat_generate.py -q`

## Role timeouts / work_mem / application_name

Applied in `20260813150000_audit_chain_role_timeouts_v1.sql` and introspected via
`pg_roles.rolconfig` (login as the role applies GUCs; `SET ROLE` alone does not).

| Role | `statement_timeout` | `lock_timeout` | `idle_in_transaction_session_timeout` | `work_mem` | `application_name` |
| --- | --- | --- | --- | --- | --- |
| `app_api` | 15s | 2s | 5s | 8MB | `smart-rag-api` |
| `app_worker` | 60s | 5s | 15s | 16MB | `smart-rag-worker` |
| `app_checkpointer` | 30s | 3s | 10s | 16MB | `smart-rag-checkpointer` |
| `app_lightrag` | 120s | 5s | 30s | 16MB | `smart-rag-lightrag` |
| `app_audit_writer` | 15s | 2s | 5s | 8MB | `smart-rag-audit` |

Long-document Hybrid ingest (Phase 3 overlay Packet 14) does **not** change
those role defaults. `apply_long_document_write_timeouts` issues
`SET LOCAL statement_timeout = '300s'` and
`SET LOCAL idle_in_transaction_session_timeout = '180s'` inside the
embedding-ledger and canonical-write transactions only. See
[INGESTION_LIMITS.md](../ingestion/INGESTION_LIMITS.md).

### Verification SQL

```sql
SELECT rolname, rolconfig
FROM pg_roles
WHERE rolname IN (
  'app_api', 'app_worker', 'app_checkpointer', 'app_lightrag', 'app_audit_writer'
)
ORDER BY rolname;
```

## ParadeDB (independent host budget)

Does **not** consume Supabase connections. See [07-bm25-projection.md](./07-bm25-projection.md).

## Verification commands

```powershell
uv run python scripts/ci/check_migrations.py
uv run pytest tests/contract/test_connection_budgets.py -q
```

Related: [06-database-workload-isolation.md](./06-database-workload-isolation.md) ·
[08-data-dictionary.md](./08-data-dictionary.md) ·
[AUDIT_CHAIN.md](../security/AUDIT_CHAIN.md) ·
[CONFIGURATION.md](../development/CONFIGURATION.md)
