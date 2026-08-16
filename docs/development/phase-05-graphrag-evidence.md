---
title: Phase 5 GraphRAG evidence
owner: engineering-lead
status: accepted
last-reviewed: 2026-08-16
audience: engineering, reviewers
phase: 5
---

# Phase 5 — GraphRAG evidence

Canonical packet evidence and exit record for
[Phase 5](../../.cursor/plans/hybrid-graph-rag/05-phase-graphrag.md).
Packet 1 created this file; later packets appended. Phase status is
`complete` after user acceptance on 2026-08-16. Holdout stays sealed.
Combined answer quality remains Phase 6.

Related: [LIGHTRAG_CONTRACT.md](../graph/LIGHTRAG_CONTRACT.md) ·
[ADR-graph-source-identity-envelope.md](../adr/ADR-graph-source-identity-envelope.md) ·
[ADR-lightrag-runtime-attach-without-ddl.md](../adr/ADR-lightrag-runtime-attach-without-ddl.md) ·
[ADAPTER_LIFECYCLE.md](../graph/ADAPTER_LIFECYCLE.md) ·
[ADR-lightrag-identical-content-collapse.md](../adr/ADR-lightrag-identical-content-collapse.md) ·
[TOOL_VERSIONS.md](./TOOL_VERSIONS.md) ·
[CONFIGURATION.md](./CONFIGURATION.md) ·
[ADR index](../adr/README.md) ·
[2026-08-16 Phases 1–5 implementation review](../reviews/2026-08-16-phases-01-05-implementation-review.md) ·
[close-out](../reviews/2026-08-16-phases-01-05-closeout.md) ·
[docs index](../README.md)

## Prerequisites

| Prerequisite | Evidence |
| --- | --- |
| Phase 1 complete/accepted | [phase-01-foundation-evidence.md](./phase-01-foundation-evidence.md) status `accepted` |
| Phase 2 complete/accepted | [phase-02-identity-data-evidence.md](./phase-02-identity-data-evidence.md) status `accepted` |
| Phase 3 complete/accepted | [phase-03-ingestion-evidence.md](./phase-03-ingestion-evidence.md) status `accepted` |
| Phase 4 engineering-close | [ADR-phase4-engineering-close.md](../adr/ADR-phase4-engineering-close.md) continues toward GraphRAG; holdout sealed |
| User mandate | Implement Phase 5 / continue through GraphRAG (Cursor chat 2026-08-15) |

## Packet 1 — immutable LightRAG pin and complete contract qualification

### Quoted requirement

> Pin and contract-test the exact LightRAG version, storage/schema behavior,
> structured identifier/source semantics, and precomputed-keyword bypass.

### Acceptance checks restated

- Exact artifact/hash/source and required public APIs qualify against real
  PostgreSQL; PGTable needs no AGE.
- Schema/bootstrap, workspace, pool/finalization, ID/source/duplicate,
  callback, structured query, status, cancellation, deletion, and bounds tests
  pass without parsing prose or relying on undocumented fields.
- Both keyword lists produce zero keyword-extraction and answer-generation
  calls; remaining calls pass through the shared gateway.
- Identical-content sources remain independently attributable/deletable, or
  GraphRAG is disabled pending an approved disable ADR.

### Negative tests restated

Hash/version mismatch, missing class/API, hidden callback, runtime-prose
parser, source-token ambiguity/truncation, duplicate-source collapse, schema
warning/drift, unbounded provider retry, unsupported deletion result, or
main-only behavior fails qualification.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/pyproject.toml` | Direct pins `lightrag-hku==1.5.6`, `asyncpg==0.31.0`, `pgvector==0.5.0` |
| `uv.lock` | Wheel SHA-256 `81b8aa8b09c11e446f94b53dbbef8d6becd900a7a44685fca95ff59cf5c8e457`; sdist `1c5afb96db5cd9f0b13b7d8d93ce1daf5a51bf7e2f74fe5ce4fe3eb9be03e77f` |
| `.venv/Lib/site-packages/lightrag/` | Installed 1.5.6 source: `aquery_data`, enqueue content-hash dedup, `ClientManager`, `POSTGRES_WORKSPACE` override, keyword bypass |
| `packages/core/src/smart_rag_core/retrieval/graph.py` | Protocols and pin constants; no `lightrag` import |
| `packages/core/src/smart_rag_core/retrieval/lightrag_pin.py` | Lock hash + required class verification |
| `packages/core/src/smart_rag_core/retrieval/lightrag_callbacks.py` | Counted gateway callbacks |
| `packages/core/src/smart_rag_core/retrieval/lightrag_structured.py` | `aquery_data` Pydantic models |
| `packages/core/src/smart_rag_core/retrieval/lightrag_qualification.py` | Disposable-schema harness |
| `tests/fixtures/lightrag/aquery_data_success_envelope.json` | Redacted success field names from the pin docstring |
| `packages/core/src/smart_rag_core/ingestion/embeddings/policy.py` | 1024-dim embedding pin |

### Primary documentation sources (2026-08-15)

- PyPI 1.5.6: <https://pypi.org/project/lightrag-hku/1.5.6/>
- GitHub commit `b33c6b0812cddf39206e48a9810112e51f025274`: <https://github.com/HKUDS/LightRAG/tree/b33c6b0812cddf39206e48a9810112e51f025274>
- ProgramingWithCore.md: <https://github.com/HKUDS/LightRAG/blob/b33c6b0812cddf39206e48a9810112e51f025274/docs/ProgramingWithCore.md>
- Installed `lightrag/lightrag.py` `aquery_data` docstring (success field names)
- Installed `lightrag/pipeline.py` content-hash / filename duplicate records
- Installed `lightrag/kg/postgres_impl.py` `ClientManager` / `POSTGRES_*`
- Installed `lightrag/kg/pgtable_impl.py` AGE-free DDL

### Files changed (Packet 1)

- `packages/core/src/smart_rag_core/retrieval/graph.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_pin.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_callbacks.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_structured.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_qualification.py`
- `packages/core/src/smart_rag_core/retrieval/__init__.py`
- `packages/core/src/smart_rag_core/gateways/model.py`
- `packages/core/src/smart_rag_core/gateways/__init__.py`
- `tests/unit/test_lightrag_pin.py`
- `tests/contract/test_lightrag_contract.py`
- `tests/fixtures/lightrag/aquery_data_success_envelope.json`
- `docs/graph/LIGHTRAG_CONTRACT.md`
- `docs/development/phase-05-graphrag-evidence.md`
- `docs/development/TOOL_VERSIONS.md`
- `docs/development/CONFIGURATION.md`
- `docs/README.md`
- `docs/adr/README.md`
- `docs/adr/ADR-lightrag-identical-content-collapse.md`
- `docs/development/phase-04-hybrid-rag-evidence.md` (MD012 trailing blank so the docs tier can run)

`packages/core/pyproject.toml` and `uv.lock` already contained the 1.5.6 pin
before this packet's remaining implementation.

### Commands and results

DSN passwords are not logged. Packet 1 Python files type-check clean under
Pyright strict. The full-repo types tier remains red from pre-existing errors
outside this packet.

| Command | Exit |
| --- | --- |
| `uv run python scripts/check.py --tier format` | 0 |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier types` | 1 (612 pre-existing errors; Packet 1 files 0) |
| `uv run python -m pytest tests/unit/test_lightrag_pin.py tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_package_imports.py -q` | 0 |
| `uv run python -m pytest tests/contract/test_lightrag_contract.py -q` | 0 (5 passed against local Supabase Postgres) |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

Scoped Packet 1 Pyright (graph, pin, callbacks, structured, qualification,
retrieval `__init__`, gateways, pin/contract tests): 0 errors.

### Negative tests

| Fixture | Result |
| --- | --- |
| Wheel/sdist hash mismatch | `LightRagPinError` |
| AGE class selected | pin compare fails; `PGGraphStorage` is not selected |
| Rendered context parser | `ProseContextRejectedError` |
| Empty / blank / duplicate / 200-cap source IDs | `SourceIdContractError` |
| Unsupported deletion status | `LightRagQualificationError` |
| `aquery_data` failure / `no_results` envelope | `LightRagQueryFailure` |
| Runtime `pipmaster.install` | test monkeypatch raises |
| Apps/backend/worker/agents `lightrag` import | static AST scan |

### Identical-content hard gate

**Raw vendor insert failed; identity envelope restores independence.** Live
qualification against local Supabase showed `apipeline_enqueue_documents`
collapses identical synthetic text under `duplicate_kind=content_hash` when
`bind_identity=false`. The second canonical ID had no `LIGHTRAG_DOC_STATUS`
row (`identical_content_status_missing`). That vendor behavior remains
recorded in
[ADR-lightrag-identical-content-collapse.md](../adr/ADR-lightrag-identical-content-collapse.md)
(`superseded`). Production inserts use `bind_graph_source_text` per
[ADR-graph-source-identity-envelope.md](../adr/ADR-graph-source-identity-envelope.md).
The independence gate is not weakened: enveloped IDs must both exist and
delete independently; raw collapse remains the negative fixture.

### Packet 1 follow-up — identity envelope (2026-08-16)

User directed Phase 5 to continue as an expert implementation rather than
leave GraphRAG disabled. Application-owned insert text is prefixed with
`<<smart-rag-graph-source:graph_source_envelope_v1:{document_version_id}>>`.
Canonical Hybrid chunks stay unenveloped. Mapping must
`strip_graph_source_envelope` before hash/span match.

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_lightrag_pin.py -q` | 0 (17 passed) |
| `uv run python -m pytest tests/contract/test_lightrag_contract.py -q` | 0 (5 passed; independence true; raw collapse still fails) |
| `uv run python scripts/check.py --tier format` | 0 |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

### Packet 2 handoff

**Packet 2 may start** after this envelope follow-up proves independence
and the raw-collapse negative. Holdout remains sealed. Do not mark Phase 5
complete.

### Deviations

- Qualification sets `cosine_better_than_threshold=-1.0` because mock
  hash vectors have no semantic neighborhood. Not a production Graph setting.
- Harness wraps `pgvector.asyncpg.register_vector` to try `extensions` after
  `public` (local Supabase type location).
- Vendor `created_at` on `aquery_data` entities/relations is an int unix
  timestamp on this pin; models accept `str | int | float`.
- Cancel qualification uses an `asyncio.Event` gate rather than a long sleep
  so vendor LLM workers can be released before `finalize_storages`.
- Packet 2 private-schema migrations are not in this packet.

### Unverified

- `pip-audit` / advisory scan of `lightrag-hku==1.5.6` beyond lock hashes.
- Production Graph deployable settings (intentionally absent).
- Full-repo Pyright (612 pre-existing errors outside Packet 1).

### Rollback

- Remove Packet 1 adapter/qualification modules and tests.
- Revert documentation index links and envelope/collapse ADRs.
- Do not drop application schemas; Packet 1 uses disposable test schemas only.
- Keep `lightrag-hku==1.5.6` in the lock only if a later packet still needs it.

## Packet 2 — controlled private storage bootstrap and adapter-only access

### Quoted requirement

> Packet 2 — controlled private storage bootstrap and adapter-only access

### Acceptance checks restated

- Fresh and repeat bootstrap yield the reviewed private schema fingerprint with
  no ignored warning/postcondition failure.
- Runtime role performs qualified DML/query only, cannot DDL/migrate, and can
  initialize its runtime objects without schema drift; all
  browser/user/service-role-facing paths deny vendor tables.
- Pool/search path/model/dimension/finalization behavior stays inside
  connection/workload budgets.
- Repository import scan proves vendor classes are confined to the
  adapter/bootstrap modules.

### Negative tests restated

Wrong search path, `POSTGRES_WORKSPACE`, runtime DDL, public vendor object,
schema-admin DSN on runtime settings, direct anon/authenticated/service_role
read, incompatible vector config, pool leak, initialization warning,
unfinalized shutdown, or forbidden import fails closed.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `.venv/Lib/site-packages/lightrag/kg/postgres_impl.py` | `ClientManager`, `POSTGRES_*`, `RESET ALL` on pool reset, `check_tables` / `setup_table` CREATE |
| `.venv/Lib/site-packages/lightrag/kg/pgtable_impl.py` | `PGTableGraphStorage._DDL` (CREATE even when tables exist) |
| `supabase/migrations/20260812135111_langgraph_lightrag_private_v1.sql` | Schema `lightrag` + `schema_capture_status` |
| `supabase/migrations/20260812135916_roles_rls_identity_v1.sql` | `app_lightrag` NOLOGIN, capture-status RLS |
| `docs/architecture/05-database-connections.md` | FastAPI/worker LightRAG cap 4; worst-case 30 < 42 |
| `tests/contract/test_privileged_secrets_absent.py` | Forbids `bootstrap` / `BOOTSTRAP` / `migration_secret` fragments on runtime settings |

### Files changed (Packet 2)

- `supabase/migrations/20260816090000_lightrag_vendor_pgtable_v1.sql`
- `supabase/migrations/20260816090100_graph_workspace_pointer_lease_v1.sql`
- `scripts/ci/check_migrations.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_adapter.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_bootstrap.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_qualification.py`
- `packages/core/src/smart_rag_core/retrieval/graph.py`
- `packages/core/src/smart_rag_core/schema/enums.py`
- `packages/core/src/smart_rag_core/schema/__init__.py`
- `packages/core/src/smart_rag_core/settings/backend.py`
- `packages/core/src/smart_rag_core/settings/worker.py`
- `packages/core/src/smart_rag_core/settings/operations.py`
- `packages/core/src/smart_rag_core/settings/__init__.py`
- `packages/core/src/smart_rag_core/generated/database.ts`
- `scripts/ops/bootstrap_lightrag_schema.py`
- `apps/backend/src/smart_rag_api/main.py`
- `apps/worker/src/smart_rag_worker/lifecycle.py`
- `tests/unit/test_lightrag_pin.py`
- `tests/unit/test_lightrag_adapter.py`
- `tests/contract/test_lightrag_bootstrap.py`
- `tests/fixtures/lightrag/schema_fingerprint_v1.json`
- `docs/adr/ADR-lightrag-runtime-attach-without-ddl.md`
- `docs/graph/ADAPTER_LIFECYCLE.md`
- `docs/runbooks/lightrag-schema-bootstrap.md`
- `docs/graph/LIGHTRAG_CONTRACT.md`
- `docs/development/CONFIGURATION.md`
- `docs/development/phase-05-graphrag-evidence.md`
- `docs/architecture/08-data-dictionary.md`
- `docs/README.md`
- `docs/adr/README.md`
- `docs/runbooks/README.md`

Reviewed fingerprint tables (schema `lightrag`, ordered):
`lightrag_doc_chunks`, `lightrag_doc_full`, `lightrag_doc_status`,
`lightrag_entity_chunks`, `lightrag_full_entities`, `lightrag_full_relations`,
`lightrag_graph_edges`, `lightrag_graph_nodes`, `lightrag_llm_cache`,
`lightrag_relation_chunks`, `lightrag_vdb_chunks_text_embedding_3_large_1024d`,
`lightrag_vdb_entity_text_embedding_3_large_1024d`,
`lightrag_vdb_relation_text_embedding_3_large_1024d`,
`schema_capture_status`.

### Commands and results

DSN passwords are not logged. Migrations were applied as postgres to local
`127.0.0.1:54322` (no `db reset`). Types were generated with `--db-url` to
that port because `supabase gen types --local` connected to `5432` and
returned an empty `Database` object. Private `lightrag` vendor tables are
absent from generated types.

| Command | Exit |
| --- | --- |
| `uv run python scripts/ci/check_migrations.py` | 0 (40 reviewed files) |
| `uv run python -m pytest tests/unit/test_lightrag_pin.py tests/unit/test_lightrag_adapter.py tests/unit/test_phase3_graph_scope_guard.py -q` | 0 (28 passed) |
| `uv run python -m pytest tests/contract/test_lightrag_bootstrap.py tests/contract/test_lightrag_contract.py -q` | 0 (14 passed against local Supabase Postgres) |
| `uv run python scripts/check.py --tier format` | 0 |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |
| `uv run python -m pytest tests/contract/test_privileged_secrets_absent.py -q` | 1 (pre-existing: `WorkerSettings` field `supabase_storage_admin_secret` matches fragment `storage_admin`. Packet 2 fields do not use `bootstrap` / `BOOTSTRAP` / `migration_secret`.) |

### Negative tests

| Fixture | Result |
| --- | --- |
| `POSTGRES_WORKSPACE` set | `postgres_workspace_env_override` |
| `search_path=public` | `wrong_search_path` |
| `SET ROLE app_lightrag; CREATE TABLE` | `InsufficientPrivilege` |
| `SET ROLE anon` / `authenticated` / `service_role` SELECT vendor table | `InsufficientPrivilege` |
| Public `lightrag_%` tables | empty |
| Embedding dim 1536 | `schema_drift_missing_vector_table` / `incompatible_vector_config` |
| Unfinalized context manager | `finalize` in `__aexit__`; pool gone |
| Second factory after finalize | pool max ≤ 4 |
| Fatal initialize warning marker | `is_fatal_initialize_warning` true |
| `lightrag` import outside adapter/bootstrap | pin AST scan |
| Ops CLI vendor import | AST scan empty |
| Schema-admin DSN on Shared/Backend/Worker/Agent | absent |

### Deviations

- Runtime role is `SET ROLE app_lightrag` on pool init/reset, not startup GUC
  `session_authorization`, because vendor `RESET ALL` would drop a startup
  authorization. Recorded in
  [ADR-lightrag-runtime-attach-without-ddl.md](../adr/ADR-lightrag-runtime-attach-without-ddl.md)
  (`accepted`; user authorized expert-continue 2026-08-16).
- `pnpm exec supabase gen types --local` targeted port 5432; types were
  generated from `127.0.0.1:54322` instead. Vendor schema `lightrag` stays
  out of generated types by schema filter.
- Mock-mode runtime attach uses cosine floor `-1.0` (same as Packet 1
  qualification) because hash embeddings have no neighborhood. Production
  `MOCK_MODEL_MODE=false` keeps `0.2`. Do not copy `-1.0` into live Graph.

### Unverified

- Full-repo Pyright (pre-existing ~612 errors outside this packet).
- `pip-audit` of `lightrag-hku==1.5.6` beyond lock hashes.
- Managed/staging apply of the two new migrations.
- `tests/contract/test_privileged_secrets_absent.py` remains red on
  pre-existing Worker `storage_admin` (not introduced by Packet 2).
- Holdout remains sealed.

### Rollback

- Unset `LIGHTRAG_DB_URL` so API/worker stay unconfigured.
- Do not DROP vendor or workspace tables (expand-only).
- Stop using `LIGHTRAG_SCHEMA_ADMIN_DSN`.
- Do not grant CREATE on schema `lightrag` to `app_lightrag`.

### Packet 3 handoff

**Packet 3 may start.** Holdout remains sealed. Do not mark Phase 5 complete.
Packet 3 owns the durable writer, insertion, budgets, state transitions, and
backlog ETA. Workspace/pointer/lease tables exist as schema only.

## Packet 3 — durable single writer, insertion, budgets, states, and backlog ETA

### Quoted requirement

> Packet 3 — durable single writer, insertion, budgets, states, and backlog ETA

### Acceptance checks restated

- Competing workers never mutate simultaneously; durable lease PLUS application
  session advisory lock (not vendor schema lock) enforce one writer.
- Replay/crash/cancel converges to one logical source operation or quarantines
  visibly; no partial vendor success becomes Graph Ready.
- Every model/embedding call is reserved/accounted and bounded; normal vs
  maintenance budgets never mix.
- Queue/backlog/ETA/cost metrics are derived from durable rows
  (mapping-verified Graph Ready count may be zero until Packet 4 — then ETA
  must be honest `insufficient-sample`, not fake throughput).

### Files changed

| Path | Role |
| --- | --- |
| `docs/graph/WORKSPACE_LIFECYCLE.md` | Seven-state `stateDiagram-v2`, lock key, recovery, admission, metrics |
| `supabase/migrations/20260816100000_lightrag_job_heartbeat_budget_v1.sql` | Heartbeat/complete/fail, writer occupy/heartbeat/release, quarantine/transition, reconciliation enqueue, budget kinds, bulk-window stub |
| `scripts/ci/check_migrations.py` | Allowlist the Packet 3 migration |
| `packages/core/src/smart_rag_core/jobs/graph_writer.py` | Lease + session `pg_advisory_lock` helpers |
| `packages/core/src/smart_rag_core/jobs/graph_index_service.py` | Eligibility revalidation, insert/delete/rebuild/reconcile, stay `updating` |
| `packages/core/src/smart_rag_core/jobs/graph_source_text.py` | Ordered `document_chunks.raw_text` |
| `packages/core/src/smart_rag_core/jobs/graph_metrics.py` | Backlog/ETA/cost from durable rows |
| `packages/core/src/smart_rag_core/retrieval/lightrag_indexer.py` | `GraphIndexer` impl; no `import lightrag` |
| `packages/core/src/smart_rag_core/retrieval/lightrag_adapter.py` | Envelope `ainsert` / status / delete |
| `packages/core/src/smart_rag_core/retrieval/lightrag_callbacks.py` | `pre_provider_hook` before embed/LLM |
| `packages/core/src/smart_rag_core/jobs/lightrag_repository.py` | Heartbeat/complete/fail/validate |
| `packages/core/src/smart_rag_core/jobs/admission.py` | `graph_index` / `graph_maintenance` reservations |
| `apps/worker/src/smart_rag_worker/graph_runner.py` | BM25-style claim/commit/heartbeat; no vendor import |
| `apps/worker/src/smart_rag_worker/lifecycle.py` | Graph poll every cycle, even while ingestion is busy |
| `packages/core/src/smart_rag_core/generated/database.ts` | Regenerated from `127.0.0.1:54322` |
| `tests/unit/test_graph_writer.py` | Lock key, states, envelope basename |
| `tests/unit/test_lightrag_indexer.py` | Insert args, replay skip, timeout-after-send, failed status |
| `tests/unit/test_graph_metrics.py` | `insufficient-sample` ETA |
| `tests/contract/test_graph_writer.py` | Two-worker exclusion, lock, lease-loss quarantine, budget kinds, RPCs, runtime DDL denied |

### RPCs (`app_worker` only; `REVOKE PUBLIC`)

- `heartbeat_lightrag_index_job`
- `complete_lightrag_index_job` (does not change `document_versions.status`)
- `fail_lightrag_index_job`
- `validate_active_lightrag_lease`
- `occupy_graph_writer_lease`
- `heartbeat_graph_writer_lease`
- `release_graph_writer_lease`
- `validate_active_graph_writer_lease`
- `quarantine_graph_workspace`
- `transition_graph_workspace_state`
- `enqueue_graph_reconciliation_job`

`reject_restricted_graph_index_job` skips the eligibility gate when
`payload_ref.reconciliation` is true so lock-loss reconciliation can insert
without a document/version.

### State machine summary

Durable states: `building`, `active`, `updating`, `filtered_dirty`,
`quarantined`, `disabled`, `retired`.

- Successful **index** leaves workspace **`updating`**. Packet 3 does not
  return `active` (maps unverified).
- Targeted delete/ACL success → `filtered_dirty`.
- Lock/lease loss, unverified vendor status, or vendor `failed` →
  `quarantined` plus reconciliation job.
- Rebuild isolates `{workspace_key}__rebuild` in `building` and does **not**
  switch the pointer.
- Public version status stays `graph_pending`. Vendor `processed` authorizes
  Packet 4 only.

Writer serialization: singleton `app.graph_writer_lease` plus session
`pg_advisory_lock` derived from `smart-rag-graph-writer-v1:{workspace_key}`.
Not the vendor schema-migration lock. No transaction is held across
extraction. `writer_lease_occupied` and `advisory_lock_busy` fail the job
transiently without quarantine.

### Commands and results

DSN passwords are not logged. The Packet 3 migration was applied as postgres
to local `127.0.0.1:54322`. Types used `--db-url` to that port. No commit,
no push, no `uv sync --package smart-rag-core`. Holdout remains sealed.
Phase status remains `pending`.

| Command | Exit |
| --- | --- |
| `uv run python scripts/ci/check_migrations.py` | 0 (41 reviewed files) |
| `uv run python -m pytest tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_lightrag_pin.py tests/unit/test_lightrag_adapter.py tests/unit/test_graph_writer.py tests/unit/test_lightrag_indexer.py tests/unit/test_graph_metrics.py tests/unit/test_job_backoff_admission.py tests/contract/test_job_leases.py tests/contract/test_graph_eligibility_storage.py tests/contract/test_graph_writer.py -q` | 0 (62 passed, including `test_graph_handoff_pause_blocks_index_claims`) |
| `uv run python -m pytest tests/contract/test_hybrid_lifecycle.py tests/contract/test_lightrag_bootstrap.py tests/contract/test_lightrag_contract.py -q` | 0 (21 passed) |
| `uv run python scripts/check.py --tier format` | 0 |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

### Deviations

- After successful index the workspace stays **`updating`** until Packet 4
  verifies maps. It does not lie `active`.
- Rebuild is isolation-only (`company_default__rebuild` in `building`). A
  second LightRAG instance cannot share this process (Packet 2). Corpus
  reindex remains Packet 7.
- Pointer attach when null does **not** bump generation (not Packet 7).
- No new env vars; graph job and writer leases reuse `JOB_LEASE_SECONDS`.
- Mapping-verified count reads `document_versions.status = 'graph_ready'`
  from `jobs/graph_metrics.py` only (outside the Phase 3 scope-guard scan)
  and stays zero.
- Bulk onboarding window is schema-only on `company_settings`; null means
  inactive. No admin UI and no invented window.
- LightRAG provider spend is reserved/true-up on `graph_index` /
  `graph_maintenance` plus `CountedLightRagCallbacks`. Hybrid
  `app.record_embedding_ledger` stays the ingest embedding path so graph
  spend never mixes into `ingestion_daily`.
- `lightrag_indexer.py` does not import `lightrag`; it was not added to
  `ALLOWED_LIGHTRAG_IMPORT_PARTS`.

### Unverified

- Live vendor `ainsert` against a full corpus under the writer loop (contract
  tests mock/exclude concurrent mutations and prove RPCs/DDL denial).
- Managed/staging apply of `20260816100000_lightrag_job_heartbeat_budget_v1.sql`.
- Full-repo Pyright (pre-existing errors outside this packet).
- Holdout remains sealed.

### Rollback

- Unset `LIGHTRAG_DB_URL` so the graph loop stays idle.
- Do not DROP writer/workspace tables (expand-only).
- Do not grant CREATE on schema `lightrag` to `app_lightrag`.

### Packet 4 handoff

**Packet 4 may start.** Vendor `processed` does not flip ready. Mapping packet
may begin. Holdout remains sealed. Do not mark Phase 5 complete. Phase status
remains `pending`.

## Packet 4 — canonical graph evidence mapping and Graph Ready

### Quoted requirement

> Packet 4 — canonical graph evidence mapping and Graph Ready

### Acceptance checks restated

- Every Graph Ready document has complete source/chunk/entity/statement/path
  map rows with accepted canonical passage support, overall and signed
  per-language gates, and reproducible config/provenance.
- One document causes at most one scoped Hybrid mapping retrieval and one
  bounded support rerank batch, not N calls.
- Unmapped/stale/ambiguous/truncated/below-threshold objects are unavailable
  plus repair diagnostics and cannot contribute to Graph Ready/query.
- Replay yields stable application IDs and no duplicate mapping/source
  readiness.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `supabase/migrations/20260816120000_graph_mapping_ready_v1.sql` | Expand-only map columns, repair, telemetry, worker RLS |
| `packages/core/src/smart_rag_core/retrieval/graph_mapping.py` | Identities, hash/span/overlap, coverage, one-shot Hybrid/rerank |
| `packages/core/src/smart_rag_core/jobs/graph_mapping_service.py` | Vendor enumerate, Graph Ready txn |
| `packages/core/src/smart_rag_core/jobs/graph_mapping_persist.py` | Map upserts (jobs/ not scope-scanned) |
| `packages/core/src/smart_rag_core/retrieval/lightrag_adapter.py` | Unqualified vendor catalog reads |
| `packages/core/src/smart_rag_core/retrieval/hybrid_run.py` | `restrict_version_id` |
| `packages/core/src/smart_rag_core/jobs/graph_index_service.py` | Map after vendor `processed`, before complete |
| `docs/graph/MAPPING.md` | Mapping contract + mermaid |

### State machine summary

Vendor `processed` authorizes mapping. `GraphMappingService` runs outside the
extraction transaction. One application transaction upserts maps, records
telemetry/repairs, and sets `document_versions.status = graph_ready` only when
support ≥ 0.80, overall coverage ≥ 0.90, and Arabic/mixed ≥ 0.85 per language.
Workspace `updating` → `active` only if the singleton pointer already names
this workspace. Null pointer: version can still become Graph Ready; no Packet 7
switch. Gate miss keeps `graph_pending` and `maps_verified: false`. Repair does
not query Hybrid and does not lower thresholds.

### Commands and results

No commit, no push, no `uv sync --package smart-rag-core`. Holdout remains
sealed. Phase status remains `pending`. The Packet 4 migration was applied as
postgres to local `127.0.0.1:54322`. Types used `--db-url` to that port.

| Command | Exit |
| --- | --- |
| `uv run python scripts/ci/check_migrations.py` | 0 (42 reviewed files) |
| `uv run python -m pytest tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_lightrag_pin.py tests/unit/test_graph_writer.py tests/unit/test_graph_mapping.py tests/unit/test_hybrid_run.py tests/contract/test_graph_mapping.py -q` | 0 (57 passed) |
| `uv run python scripts/check.py --tier format` | 0 |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

### Deviations

- Hybrid/rerank callbacks are injected into `GraphMappingService`. Packet 4
  originally left worker construction of `HybridRetriever` unwired so `apps/`
  would not contain mapping-table strings. That hole is **resolved** by
  `bind_mapping_support` in `jobs/` (see remaining mapping Hybrid section
  below). Hash/span/overlap still run when callbacks are `None`.
- Path-edge IDs are one statement plus `src_to_tgt` plus version (ordered
  statement list of length 1). Multi-hop path composition is Packet 5+.
- No new environment variables.

### Unverified

- Live vendor catalog reads against a full LightRAG `processed` corpus (contract
  tests use a fake vendor reader on local Postgres maps).
- Managed/staging apply of `20260816120000_graph_mapping_ready_v1.sql`.
- Worker process with live OpenAI support rerank.

### Packet 5 handoff

**Packet 5 may start only if maps/ready path is proven.** Holdout remains
sealed. Do not mark Phase 5 complete. Phase status remains `pending`.

## Packet 5 — structured graph retrieval, authoritative resolver, survival, and inspection

### Quoted requirement

> Packet 5 — structured graph retrieval, authoritative resolver, survival,
> and inspection

### Acceptance checks restated

- Resolver returns only authorized current canonical IDs/locators and
  application relationship/path objects; every native lead either survives
  all checks or is dropped wholly.
- Candidate/path/hop/token/row/time limits are application-enforced,
  deterministic, and tested independently of vendor defaults.
- Survival, partial readiness, authorized-only ACL blindness, historical
  limitation, outage/quarantine, and global steering emit exact typed
  signals without information leakage.
- Query-time counters prove zero per-statement support searches and zero
  hidden keyword/answer model calls.

### Negative tests restated

Prose/reference/path as citation, stale map, current-pointer race,
deleted/ACL-restricted source, unauthorized count disclosure, native
over-limit result, hidden callback, query-time repair search, historical
path, inspection bypass, timeout leak, or low survival labeled Combined
fails.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/src/smart_rag_core/retrieval/graph.py` | `GraphRetriever` protocol, `GraphLimitationCode`, 12/3/6 and inspection bounds |
| `packages/core/src/smart_rag_core/retrieval/lightrag_structured.py` | `parse_aquery_data_payload` / `to_graph_leads`; `reject_rendered_context_parser` |
| `packages/core/src/smart_rag_core/retrieval/lightrag_adapter.py` | `aquery_data_structured`; `QueryParam` both keyword lists, `enable_rerank=False` |
| `packages/core/src/smart_rag_core/retrieval/lightrag_callbacks.py` | `CountedLightRagCallbacks` keyword/answer counters |
| `packages/core/src/smart_rag_core/retrieval/recheck.py` | ACL/current/deletion recheck patterns reused by resolver |
| `packages/core/src/smart_rag_core/jobs/graph_resolver.py` | Map-table SQL (jobs/ not scope-scanned) |
| `tests/unit/test_phase3_graph_scope_guard.py` | Forbids map-table / Graph Ready strings in `apps/` and `retrieval/` except allowlist |

### Files changed (Packet 5)

- `packages/core/src/smart_rag_core/retrieval/graph.py`
- `packages/core/src/smart_rag_core/retrieval/graph_results.py`
- `packages/core/src/smart_rag_core/retrieval/graph_retriever.py`
- `packages/core/src/smart_rag_core/retrieval/lightrag_adapter.py`
- `packages/core/src/smart_rag_core/retrieval/__init__.py` (result types only; no `retrieve_graph` re-export)
- `packages/core/src/smart_rag_core/jobs/graph_resolver.py`
- `packages/core/src/smart_rag_core/jobs/exceptions.py`
- `packages/core/src/smart_rag_core/jobs/limits.py`
- `packages/core/src/smart_rag_core/jobs/__init__.py`
- `packages/core/src/smart_rag_core/generated/database.ts`
- `supabase/migrations/20260816130000_graph_resolver_query_v1.sql`
- `scripts/ci/check_migrations.py`
- `apps/backend/src/smart_rag_api/routers/graph_inspect.py`
- `apps/backend/src/smart_rag_api/schemas/graph_inspect.py`
- `apps/backend/src/smart_rag_api/services/graph_inspect.py`
- `apps/backend/src/smart_rag_api/main.py`
- `tests/unit/test_graph_resolver.py`
- `tests/unit/test_graph_retriever.py`
- `tests/unit/test_graph_inspect_openapi.py`
- `tests/contract/test_graph_retrieval.py`
- `docs/graph/RETRIEVAL.md`
- `docs/graph/LIGHTRAG_CONTRACT.md`
- `docs/graph/MAPPING.md`
- `docs/graph/GRAPH_MAPPING_CONTRACT.md`
- `docs/graph/WORKSPACE_LIFECYCLE.md`
- `docs/ingestion/INGESTION_LIMITS.md`
- `docs/architecture/08-data-dictionary.md`
- `docs/README.md`
- `docs/development/phase-05-graphrag-evidence.md`

### Query path summary

`retrieve_graph` revalidates workspace pointer, generation, current-only
policy, caller snapshot, and remaining deadline. Workspace not `active`
with an attached pointer fails closed (`graph_outage` /
`graph_updating` / `graph_filtered_dirty`) without a vendor call.
Explicit `as_of` or `historical_relationship` emits
`temporal_graph_limitation` and skips vendor query.

Local/hybrid calls adapter `aquery_data_structured` with both keyword
lists non-empty, `only_need_context=True`, `enable_rerank=False`,
`include_references=False`. Modes are only `local` / `hybrid` /
`global`. Outer `asyncio.wait_for` cancels the query task; process
adapter `finalize` is not per query. Structured parse rejects rendered
prose. Application clamp: 12 candidates, 3 hops, 6 paths, stable
tie-breaks.

Resolver batch-rechecks maps, support ≥ 0.80, ACL, current pointer,
deletion, eligibility, mapping/config generation, and canonical passage
existence. Any required miss drops the **whole** candidate and enqueues
one `query_resolve` repair. Query-time Hybrid is never run. Canonical
locators come from `document_chunks`, never vendor chunk text.

Global steering is a separate path: at most 3 topic/entity expansions,
never evidence, signal `global_steering_only`.

Inspection is SQL-only (`app.inspect_graph_neighborhood`): depth 3, 200
rows, `statement_timeout='3s'`, 10s end-to-end. `POST /graph/inspect`
requires auth. The router contains no map-table strings.

### Signals / types

`GraphLimitationCode`: `graph_survival_below_threshold`,
`graph_partial_readiness`, `graph_acl_blindness`,
`temporal_graph_limitation`, `graph_outage`, `graph_updating`,
`graph_filtered_dirty`, `global_steering_only`, `graph_empty`,
`graph_deadline`, `graph_cancelled`.

Result envelope: `GraphRetrievalResult` with
`GraphResolvedCandidate`, `GraphPath`, `GraphCanonicalLocator`,
`GraphSteeringExpansion`, `GraphLimitation`, `GraphQueryCounters`,
`RollingSurvivalWindow`. Inspection: `GraphInspectResult` /
`GraphInspectNode`.

`graph_survival_ratio = supported_resolved / returned_graph_candidates`
(null if none). Below 0.50 emits `graph_survival_below_threshold`.
Rolling 0.80 / 20 is recorded on `app.graph_survival_samples`, not a
live alerter.

### Callback proof

`CountedLightRagCallbacks` snapshot before/after vendor query. Any
increase in `keyword_extract` or `answer_generate` fails closed as
`hidden_graph_model_call`. `GraphQueryCounters.support_searches` and
`repair_hybrid_searches` are hard-zeroed. Unit tests fail when a stub
keyword callback fires.

### RPCs / tables (`app_api`; RLS rechecks ACL)

- `app.graph_survival_samples`
- `app.enqueue_graph_map_repair` (SECURITY INVOKER)
- `app.graph_visibility_counts`
- `app.inspect_graph_neighborhood`
- GRANT SELECT + RLS `*_api_select USING (true)` on the three map tables
  (RPCs recheck `caller_can_read_document`)

### Commands and results

No commit, no push, no `uv sync --package smart-rag-core`. Holdout remains
sealed. Phase status remains `pending`. The Packet 5 migration was applied
as postgres to local `127.0.0.1:54322`. Types used `--db-url` to that
port.

| Command | Exit |
| --- | --- |
| `uv run python scripts/ci/check_migrations.py` | 0 (43 reviewed files) |
| `uv run python -m pytest tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_lightrag_pin.py tests/unit/test_graph_mapping.py tests/unit/test_graph_resolver.py tests/unit/test_graph_retriever.py tests/unit/test_graph_inspect_openapi.py tests/contract/test_graph_retrieval.py -q` | 0 (59 passed) |
| `uv run python scripts/check.py --tier format` | 0 (396 files) |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

### Deviations

- `enqueue_graph_map_repair` is SECURITY INVOKER plus `app_api` RLS, not
  DEFINER, because FORCE RLS would otherwise block DEFINER writes.
- Restricted documents cannot be `documents.graph_eligible` (CHECK needs
  `current_version_id` and `company_visible`). Inspection of a restricted
  document returns empty rows / no names rather than member-visible
  restricted graph nodes. ACL blindness still counts restricted
  graph-ineligible versions the caller can read.
- `retrieve_graph` is not re-exported from `retrieval/__init__.py`
  (circular import: jobs → retrieval.graph → package `__init__` →
  graph_retriever → jobs.graph_resolver). Callers import
  `smart_rag_core.retrieval.graph_retriever`.
- `GRAPH_SURVIVAL_ROLLING_WINDOW = 20` is duplicated in `graph.py` and
  `jobs/limits.py`.
- Combined fallback / relabel on low survival is Phase 6. Packet 5 emits
  `graph_survival_below_threshold` only.
- Rolling 0.80 / 20 is a recorded counter/interface, not a live alert
  backend.

### Unverified

- Live LightRAG `aquery_data` against a full corpus (contract tests use a
  fake retriever plus SQL maps). Adapter `QueryParam` is unit-tested with
  a stub `rag`.
- Managed/staging apply of `20260816130000_graph_resolver_query_v1.sql`.
- Full-repo Pyright (pre-existing errors outside this packet).
- Combined answer quality / holdout remain sealed.

### Rollback

- Unset `LIGHTRAG_DB_URL` so query/inspection stay idle.
- Do not DROP map/survival/repair tables (expand-only).
- Remove `POST /graph/inspect` router include if the API surface must be
  withdrawn.

### Packet 6 handoff

**Packet 6 may start if resolver/inspection are proven.** Holdout remains
sealed. Do not mark Phase 5 complete. Phase status remains `pending`.
Packet 6 owns entity curation, extraction policy, invalidation, and
rebuild scheduling — not Combined answers/SSE.

## Packet 6 — entity curation, extraction policy, invalidation, and rebuild scheduling

### Quoted requirement

> Packet 6 — entity curation, extraction policy, invalidation, and rebuild
> scheduling

### Acceptance checks restated

- Approved rules deterministically affect canonical keys/extraction on
  rebuild; ambiguous/do-not-merge entities never silently merge.
- Suggested/revoked rules cannot affect active graph results; changes
  invalidate mappings and schedule versioned clean rebuild.
- Rule CRUD is authorized/audited and cannot broaden graph eligibility or
  Hybrid aliases.

### Negative tests restated

Member/viewer mutation, stale concurrent update, cross-type alias, cycle,
auto-approval, inactive suggestion use, direct vendor patch, native-to-Hybrid
alias copy, or rule change without invalidation/rebuild fails.

### Canonical keys

Application merge identity is `{TYPE}::{normalized_name}` after
`normalize_for_dedup` (type uppercased). `PROJECT::atlas` is never
`PRODUCT::atlas`. `canonical_entity_key` hashes `graph_pipeline_v1` plus
that typed key. Do-not-merge wins. Missing vendor type does not consume a
typed alias. Suggested/revoked rows are not loaded.

### Schema / RPCs

Expand-only `20260816140000_graph_entity_rules_v1.sql` on stub
`app.graph_entity_rules` (kept `rule jsonb`, dual-written from typed
columns). Added status `suggested|approved|revoked`, aliases, do-not-merge,
languages, alias scope/effective dates, display labels, relation-label
policy, `row_version`, reason/source/confidence/provenance, and
`app.graph_extraction_policy` singleton.

- `app.upsert_graph_entity_rule` / `approve_graph_entity_rule` /
  `revoke_graph_entity_rule` / `list_graph_entity_rules`
- `app.apply_entity_rule_graph_invalidation` (DEFINER; worker execute)
- Feedback/model cannot INSERT as approved (`auto_approval_forbidden`)
- `active` iff `status = approved`

### Invalidation and rebuild

`GRAPH_PIPELINE_VERSION` stays `graph_pipeline_v1`. Approved
create/update/approve/revoke bumps `entity_rules_generation`, prefixes live
map `config_generation` with `invalidated:`, sets Graph Ready versions to
`graph_pending`, upserts `map_repair`, and enqueues
`graph_entity_rules_rebuild:{workspace}:{generation}` with
`isolate_only=true`. Isolation workspace is `company_default__rebuild` in
`building`. Pointer generation is unchanged. Packet 7 owns the switch.

Generation `1` with an empty extraction hash keeps Packet 5 mapping digests
until the first bump. Default extraction overlay hash is
`b8719e2481b2f8ed85be76d13e19c092428e92ffdf3d36bcd5e5e9656c65bd08`.

### Authorization / audit

Owner/admin only via `CallerContextDep` plus SQL `validate_caller_context`.
Members/viewers receive `403 forbidden`. MFA is inherited from
`profile_loader` (owner/admin already require enrolled MFA + AAL2). Stale
`row_version` is `409`. Append-only `app.audit_events` records
`graph.entity_rules.upserted|approved|revoked` without corpus text. Rules
cannot set `graph_eligible` or write `search_aliases`.

### Routes

`GET/POST /admin/graph/entity-rules`, `PATCH /{id}`,
`POST /suggestions`, `POST /{id}/approve`, `POST /{id}/revoke`.

### Commands and results

No commit, no push, no `uv sync --package smart-rag-core`. Holdout remains
sealed. Phase status remains `pending`. The Packet 6 migration was applied
as postgres to local `127.0.0.1:54322`. Types used `--db-url` to that port
with separate `--schema` flags (comma-joined `--schema` produced an empty
`Database`).

| Command | Exit |
| --- | --- |
| `uv run python scripts/ci/check_migrations.py` | 0 (44 reviewed files) |
| `uv run python -m pytest tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_lightrag_pin.py tests/unit/test_graph_mapping.py tests/unit/test_graph_resolver.py tests/unit/test_entity_rules.py tests/unit/test_entity_rules_openapi.py tests/contract/test_entity_rules.py -q` | 0 (65 passed) |
| `uv run python scripts/check.py --tier format` | 0 (406 files) |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

### Deviations

- `canonical_entity_key` now hashes the typed `{TYPE}::{name}` string
  instead of separate type+name digest parts.
- `mapping_config_generation` omits `entity_rules_generation` /
  `extraction_policy_hash` at generation `1` so Packet 5 map digests stay
  stable until the first approved-rule bump.
- Rule CRUD is SECURITY DEFINER (glossary equivalent), not INVOKER, because
  `app_api` cannot UPDATE map tables.
- Isolated entity-rule rebuild jobs (`document_id` null,
  `payload_ref.isolate_only=true`) skip `assert_graph_index_allowed`,
  matching the existing reconciliation skip. They do not attach a document
  or broaden `graph_eligible`.
- SQL treats alias-equal-to-canonical (after `arabic_norm_v1`) as redundant,
  not `duplicate_alias`. Self-edges are excluded from cycle detection.
- Invalidation returns every `graph_ready` version to `graph_pending`, not
  only the live workspace.

### Unverified

- Live LightRAG rebuild against `company_default__rebuild` (Packet 7 switch
  is not this packet).
- Managed/staging apply of `20260816140000_graph_entity_rules_v1.sql`.
- `supabase_migrations.schema_migrations` still lacks `20260816130000`
  (Packet 5 objects exist; Packet 6 recorded `20260816140000` only).
- Full-repo Pyright (pre-existing errors outside this packet).
- Combined answer quality / holdout remain sealed.

### Rollback

- Do not DROP expanded `graph_entity_rules` columns or
  `graph_extraction_policy` (expand-only).
- Remove `entity_rules_router` include if the API surface must be withdrawn.
- Revoke approved rules to stop them loading; maps stay invalidated until a
  later rebuild/switch.

### Packet 7 handoff

**Packet 7 may start if rules+invalidation are proven.** Holdout remains
sealed. Do not mark Phase 5 complete. Phase status remains `pending`.
Packet 7 owns atomic version switching, deletion/ACL cleanup, upgrade,
rollback, and disablement — not Combined answers/SSE.

## Packet 7 — atomic version switching, deletion/ACL cleanup, upgrade, rollback, and disablement

### Quoted requirement

> Packet 7 — atomic version switching, deletion/ACL cleanup, upgrade,
> rollback, and disablement

### Acceptance checks restated

- Pointer crashes expose old or new generation, never mixed/zero current
  versions; post-flip cleanup is retryable and filtered.
- Deletion/ACL exclusion is immediate at resolver, targeted deletion/cache
  cleanup verifies within 24 hours, and clean rebuild from surviving sources
  verifies within seven days.
- Shared-entity and identical-content fixtures prove no deleted/restricted
  evidence survives canonical resolution/inspection.
- Upgrade qualification uses a restored isolated copy; failed
  migration/rebuild can restore/disable safely; embedding configs never mix.

### Negative tests restated

Crash before/during/after pointer commit, stale generation, concurrent
delete, delete `not_found`/`not_allowed`/`fail`, recovery-phase crash, cache
residue, source residue, shared-entity contamination, ACL race, unfunded
rebuild, schema warning/drift, incompatible rollback, or automatic ACL
expansion all fail safe.

### Pointer CAS contract

Short application transaction only. Vendor/model work stays outside it.

1. `pg_advisory_xact_lock(hashtext('smart-rag-graph-pointer-v1'), hashtext(workspace_key))`
2. Lock `app.graph_active_workspace_pointer` and source rows `FOR UPDATE`
3. Compare expected generation / current version / workspace; recheck
   deletion/ACL
4. Same-workspace version flip: `documents.current_version_id`, `is_current`,
   Hybrid/BM25 visibility generation, map `retrieval_eligible`, tombstone,
   audit. **Does not bump generation** (map `config_generation` stays valid)
5. Workspace rebuild/upgrade flip: CAS `generation = generation + 1`, retire
   old workspace, activate target, homogeneous embedding pin
6. After commit: serialized `adelete_by_doc_id` for the old vendor document;
   failure leaves old derived rows filtered and retryable

Crashes expose exactly one current version and one positive generation.

### Delete / ACL / tombstone SLAs

| Gate | Behavior |
| --- | --- |
| Immediate | Phase 3 canonical exclusion / `retrieval_eligible=false` is resolver authority. Recheck before vendor mutate |
| Vendor | `adelete_by_doc_id(..., delete_llm_cache=True)`. Persist every recovery phase. No entity/relation graph surgery |
| Success | Workspace `filtered_dirty`; tombstone `target_cleanup_at` = now+24h; `clean_rebuild_at` = now+7d; surviving-source rebuild `isolate_only=true` |
| Fail closed | `not_allowed` / `fail` / timeout / residue / resolver failure → `quarantined` + `Deletion cleanup failed`. Inspection/Combined already `graph_outage` |
| `not_found` | Clean only after residue verification; residue → `not_found_with_residue` quarantine |
| Unfunded rebuild | Canonical exclusion remains; enqueue refused; workspace quarantines until funded |
| ACL expansion | `set_document_visibility` restricted→company_visible does **not** insert `index` or `graph_acl_remove` |

### Upgrade isolation

- Parallel versioned workspace, one homogeneous config
  (`text-embedding-3-large` / 1024). Table CHECKs refuse in-place mix.
- LightRAG package/schema upgrade: restore a production-sized snapshot into
  a **separate database** (preferred) or different schema. A second workspace
  in runtime `lightrag` records `refused_same_schema`.
- Ops: `scripts/ops/restore_lightrag_upgrade_copy.py` plus
  [GRAPH_SNAPSHOT_RESTORE_ROLLBACK.md](../runbooks/GRAPH_SNAPSHOT_RESTORE_ROLLBACK.md)
- Snapshot/restore = vendor schema rollback. Pointer rollback = application
  data compatible with the current schema only.
- Two consecutive failed qualifications or survival alerts below 0.80 for
  seven days → disable review. No silent provider substitution.

### Schema / jobs

Expand-only `20260816150000_graph_pointer_switch_cleanup_v1.sql`:

- `retrieval_eligible` on source/chunk/evidence maps
- `app.graph_cleanup_tombstones`, `app.graph_upgrade_qualifications`
- `assert_graph_build_index_allowed` for non-current pending-switch index
- `switch_graph_document_version`, `switch_graph_active_workspace`,
  `disable_graph_workspace`, `record_graph_upgrade_qualification`,
  `upsert_graph_cleanup_tombstone`, exclusion triggers
- Inspection RPC also requires `retrieval_eligible`

Local `supabase_migrations.schema_migrations` now includes
`20260816130000` (Packet 5 objects already existed) and `20260816150000`.
`20260816140000` was already recorded. Old migrations were not rewritten.

### Commands and results

No commit, no push, no `uv sync --package smart-rag-core`. Holdout remains
sealed. Phase status remains `pending`. The Packet 7 migration was applied
as postgres to local `127.0.0.1:54322`. Types used `--db-url` to that port
with separate `--schema` flags.

| Command | Exit |
| --- | --- |
| `uv run python scripts/ci/check_migrations.py` | 0 (45 reviewed files) |
| `uv run python -m pytest tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_lightrag_pin.py tests/unit/test_graph_resolver.py tests/unit/test_entity_rules.py tests/unit/test_graph_lifecycle.py tests/contract/test_graph_lifecycle.py -q` | 0 (66 passed) |
| `uv run python -m pytest tests/unit/test_graph_mapping.py -q` (with the suite above) | 0 (80 passed including mapping) |
| `uv run python scripts/ops/restore_lightrag_upgrade_copy.py --candidate-database postgres --candidate-schema lightrag --runtime-database postgres --runtime-schema lightrag` | 2 (`upgrade_same_schema_insufficient`) |
| `uv run python scripts/check.py --tier format` | 0 (413 files) |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 |

### Deviations

- `lightrag_source_map` remains PK `document_id`. Pending-switch maps do not
  overwrite a live eligible row; the version-switch txn retargets that
  singleton onto the new `version_id` and sets it eligible.
- Same-workspace version switch does not bump pointer generation so live map
  `config_generation` digests stay valid. Workspace switch does bump it.
- SQL pointer xact lock uses `hashtext`; Python tests use SHA-256 helpers
  for the writer-style key pair and do not need to match `hashtext`.
- `record_graph_upgrade_qualification` records `refused_same_schema` and
  returns the row id instead of raising, so the refuse is durable in the
  caller transaction. Python `assert_isolated_upgrade_environment` still
  fail-closes before SQL.
- Local dump restore into a second Postgres database is ops-scripted; this
  host may lack `createdb`/`pg_restore`. Same-schema refuse is the local
  proof.

### Unverified

- Live LightRAG `adelete_by_doc_id` against vendor tables for post-flip
  cleanup (SQL/map residue and fail-closed statuses are tested).
- Production-sized snapshot restore into a disposable second database.
- Managed/staging apply of `20260816150000_graph_pointer_switch_cleanup_v1.sql`.
- Full-repo Pyright (pre-existing errors outside this packet).
- Combined answer quality / holdout remain sealed.

### Rollback

- Do not DROP `retrieval_eligible`, tombstones, or qualification tables
  (expand-only).
- Disable the workspace or unset `LIGHTRAG_DB_URL` so query/inspection stay
  idle (`graph_outage`).
- Vendor schema rollback is snapshot restore into an isolated copy, then a
  verified pointer switch or disable. Pointer rollback cannot undo an
  incompatible vendor schema.

### Packet 8 handoff

**Packet 8 started after switch+delete+quarantine were proven.** Holdout
remains sealed. Do not mark Phase 5 complete. Phase status remains
`pending`. Packet 8 owns graph evaluation, envelope proof, scaling options,
and the Phase 6 handoff — not Combined answers/SSE.

## Packet 8 — graph evaluation, envelope proof, scaling options, and Phase 6 handoff

### Quoted requirement

> Packet 8 — graph evaluation, envelope proof, scaling options, and Phase 6
> handoff

### Acceptance checks restated

- Signed overall/per-language extraction/mapping/survival gates pass on
  qualification data; no holdout leakage.
- Hidden keyword/query-answer call count and query-time per-statement
  Hybrid/model count are zero; all expected calls/costs are bounded/accounted.
- Resolver/inspection returns no unauthorized/stale/deleted/superseded/
  native-prose evidence under every fixture and obeys all bounds.
- Measured throughput/rebuild/cost/SLA proves the signed envelope/reserve
  or the supported envelope is explicitly reduced before graph launch.
- Phase 6 receives frozen interfaces/fixtures and an explicit no-claim for
  Combined answer quality; user acceptance precedes status change.

### Negative tests restated

Aggregate-only language pass, unmapped returned relation, hidden callback,
N-search, unauthorized ACL count, historical path, inspection overrun,
subjective throughput extrapolation, unfunded reserve, unexecuted Phase 6
label counted as pass, or holdout access fails. Combined +10pp quality is
not a Packet 8 pass. Query-agent / SSE / Combined fusion are Phase 6.

### Frozen manifest

Location: [FROZEN_GRAPH_MANIFEST.md](../graph/FROZEN_GRAPH_MANIFEST.md).
Regenerated by `uv run python scripts/eval_phase5_graph_freeze.py` from
`smart_rag_core.evaluation.graph_eval` (not imported from
`evaluation.__init__`, same cycle-avoidance as Phase 4 freeze).

| Pin / hash | Value |
| --- | --- |
| Packets 1-7 pin commit | `c546f9c` (`c546f9c2ff88fc9fd0e710f802fe61b0a9bb9f54`) |
| Working-tree `git rev-parse HEAD` | `c546f9c2ff88fc9fd0e710f802fe61b0a9bb9f54` (Packet 8 uncommitted) |
| LightRAG | `1.5.6` / commit `b33c6b0812cddf39206e48a9810112e51f025274` |
| Wheel SHA-256 | `81b8aa8b09c11e446f94b53dbbef8d6becd900a7a44685fca95ff59cf5c8e457` |
| Graph storage | `PGTableGraphStorage` only |
| Schema fingerprint SHA-256 | `76f10dcd3b4f64736b5b1d32961f375b4b60f224ea865bd06dfa3e46114977dc` |
| Embedding | `text-embedding-3-large` @ 1024 |
| Chunker | 1200 / 100 / `gpt-4o-mini` |
| `GRAPH_PIPELINE_VERSION` | `graph_pipeline_v1` |
| `GRAPH_FIELD_SEP` | `<SEP>` |
| Entity-rules generation | `1` |
| Extraction policy hash | `b8719e2481b2f8ed85be76d13e19c092428e92ffdf3d36bcd5e5e9656c65bd08` |
| Workspace config generation | `8222c35ccc95225538d081203d3453eab72ce203500d68b4216cf48e7867a850` |
| Adapter bounds | 12 candidates / 3 hops / 6 paths |
| Inspect bounds | depth 3 / 200 rows / 3s `statement_timeout` / 10s deadline |
| Support / coverage | ≥ 0.80 / overall-en ≥ 0.90 / ar-mixed ≥ 0.85 |
| Survival | fallback 0.50; rolling 0.80 / 20 |
| Development manifest SHA-256 | `e0691e5de6b1df4f5999ac38e74dbd151cd816b5ad647b909d7b1afe9826281e` |
| Qualification manifest SHA-256 | `d4f91781bdfe3c333dd1ec77818ead241dbd6b066df824ae8a1fd1238a47d736` |
| Holdout id-list SHA-256 (labels not opened) | `f5887ac8704bf4f97eb0e18bdaf76976265d2fed01e22ee4d977ea3a633d0fa6` |

Holdout loaders were not used. `HoldoutAccess.from_settings()` must remain
`denied()`. Freeze refuses to run if holdout access is enabled.

### Per-language / per-type metrics

Recorded in [PHASE5_GRAPH_EVAL.md](../evaluation/PHASE5_GRAPH_EVAL.md).

| Language | Types | Accepted/eligible | Floor | Result |
| --- | --- | --- | --- | --- |
| `en` | entity, relation, path_edge | 20/20 (1.00) | 0.90 | pass_fixture |
| `ar` | entity, relation, path_edge | 17/20 (0.85) | 0.85 | pass_fixture |
| `mixed` | entity, relation, path_edge | 17/20 (0.85) | 0.85 | pass_fixture |

These are **CoverageSlice gate-contract fixtures**, not live LightRAG
extraction P/R. Mixed is not averaged under English totals
(`test_mixed_language_is_not_hidden_by_english_totals` plus
`failing_mixed_hidden_by_english_slices`). Unmapped returned relations:
`0` (`test_unsupported_relation_has_no_statement_id`).

Qualification open-split class counts used as labels only (not extraction
gold): `graph_mapping` 4, `relationship` 6, `multi_hop` 6, `arabic_mixed` 4.
Open-split `graph_mapping` documents (dev+qual) = **15**. GRAPH_MAPPING
rows are query labels.

Gate `P8-EXTRACT-LIVE` is **unverified**. Do not treat fixture floors as a
live corpus pass.

### Call accounting

| Counter | Value | Cited proof |
| --- | --- | --- |
| query `keyword_extract` | 0 | `test_query_callbacks_bounds_delete_status_and_cancel`; `test_hidden_keyword_callback_fails_closed` |
| query `answer_generate` | 0 | same contract spy |
| query `support_searches` | 0 | resolver has no per-statement Hybrid; `test_repair_must_not_query_hybrid` |
| mapping Hybrid max / document | 1 | `test_unresolved_batch_uses_one_hybrid_and_one_rerank` |
| mapping rerank max / document | 1 | same |

Packet 8 aggregator: `tests/unit/test_graph_eval.py`.

### Fixture sweep (Packets 5-7 reused)

Checklist is generated into PHASE5_GRAPH_EVAL and asserted by
`test_fixture_sweep_covers_required_packets_5_to_7_invariants`.

| Id | Packet | Invariant |
| --- | --- | --- |
| collisions_aliases_do_not_merge | 6 | `PROJECT::atlas` stays distinct from `PRODUCT::atlas` |
| global_steering | 5 | global expansions are steering only |
| mapping_repair | 4 | repair does not run query-time Hybrid |
| low_survival | 5 | survival < 0.50 → `graph_survival_below_threshold` |
| partial_readiness | 5 | count never names restricted documents |
| temporal_limitation | 5 | historical/`as_of` skips vendor |
| acl_blindness_versus_unauthorized_silence | 5 | authorized count; unauthorized silence |
| version_overlap | 7 | exactly one current version |
| deletion_acl_shared_source | 7 | deleted/restricted shared-source does not survive |
| filtered_quarantined_disabled | 7 | query path is `graph_outage` |
| upgrade_rollback_refuse_same_schema | 7 | same-schema upgrade refused |
| unfunded_rebuild_quarantine | 7 | unfunded rebuild quarantines |
| tombstone_24h_7d | 7 | 24h target / 7d dirty; live SLA unverified |
| inspection_bounds | 5 | depth 3 / 200 rows / 3s / 10s |
| adapter_bounds | 5 | 12 / 3 / 6 |

### Bound benchmarks

Proven by unit/contract timeouts, not Combined stream p95:

- 12 candidates, 3 hops, 6 paths
- inspect depth 3 / 200 rows / 3s `statement_timeout` / 10s deadline
- Combined stream p95: **not measured** (Phase 6)

Pytest durations (slowest Packet 8-relevant calls, this host): pin verify
0.82s; scope guard 0.66s; graph_eval open-split count 0.31s. These are
fixture runtime lower bounds, not production documents/hour.

### Envelope, throughput, cost, reserve (reduced)

Plan default remains 2,000 current documents / 200,000 source chunks with
a 7-day clean rebuild. Packet 8 **did not measure** a live mapping-verified
documents/hour or a full-rebuild cost.

| Quantity | Value |
| --- | --- |
| Sequential 7-day cap at 600s index deadline | 1,008 documents (`7*86400/600`) |
| Plan 2,000 inside 7 days sequential | **false** (2000 > 1008) |
| Advertised supported documents | **15** (open-split labeled `graph_mapping`) |
| Advertised supported source chunks | **unverified** (not 200,000) |
| Bulk onboarding | **blocked** |
| Measured full-rebuild cost | **unverified** |
| Maintenance reserve | **USD 800** floor (`4 x measured` unevaluable) |
| Unfunded rebuild | already quarantines (Packet 7) |
| 24h delete / 7d dirty consolidation | tombstone constants proven; **live production SLA unverified** |

Quality-target rows: QT-CAP-005-P8 / QT-CAP-006-P8 in
[QUALITY_TARGETS.md](../QUALITY_TARGETS.md) section 14. Options to raise
later: [SCALING_OPTIONS.md](../graph/SCALING_OPTIONS.md).

### Scaling options (not implemented)

[SCALING_OPTIONS.md](../graph/SCALING_OPTIONS.md) records options only:

1. Domain / security-boundary sharding
2. Dedicated managed LightRAG PostgreSQL behind protocols
3. Qualified incremental compaction/rebuild
4. Hybrid-only disablement

Triggers and decision inputs are listed. No sharding, dedicated DB,
incremental rebuild, or Hybrid-only productization was implemented.

### Phase 6 handoff

Location: [PHASE6_HANDOFF.md](../graph/PHASE6_HANDOFF.md).

Frozen for Phase 6: `GraphRetriever`, `GraphLeadSet`, `GraphQueryBounds`,
`GraphRetrievalResult`, `GraphInspectResult`, `retrieve_graph`,
`hl_keywords` / `ll_keywords`, `{TYPE}::{name}` keys, statement/path IDs,
limitation codes (`graph_survival_below_threshold`,
`graph_partial_readiness`, `graph_acl_blindness`,
`temporal_graph_limitation`, `graph_outage`, workspace states), inspection
bounds, and development/qualification `relationship` / `multi_hop` /
`graph_mapping` labels.

Explicit no-claim (must appear as a single line in the handoff):

> Phase 6 owns Combined fusion, verifier/citations in final answers, the
> immutable launch holdout, and the at-least-10-point relationship/multi-hop
> gain over Hybrid (QT-EVAL-009).

Phase 5 proves infrastructure, mapping, resolver, and envelope only. An
unexecuted Phase 6 label is not a Packet 8 pass.

### `Done when` mapping (Phase 5 wrapper)

| Wrapper `Done when` fragment | Packet 8 evidence |
| --- | --- |
| Artifact-hashed LightRAG / PGTable / no AGE / callbacks / deletion | Packets 1-2 plus pin tests in this packet's pytest list |
| Single writer, lease, states `building`/`active`/`updating`/`filtered_dirty`/`quarantined`/`disabled`/`retired` | Packets 3 and 7; lifecycle tests reused |
| Graph Ready mapping thresholds; unmapped dropped; repair | Packet 4; coverage fixtures; `P8-MAP-LANG` / `P8-SUPPORT` |
| No N-per-statement search; zero hidden keyword/answer | `P8-CALLBACKS`; mapping one Hybrid + one rerank |
| Authorized current canonical IDs plus confidence | Packets 5-7 resolver/inspection fixtures |
| Historical → temporal limitation; no superseded paths | `temporal_limitation` sweep |
| Authorized ACL blindness vs unauthorized silence | `acl_blindness_versus_unauthorized_silence` |
| Entity alias/type/do-not-merge | Packet 6 sweep |
| Pointer flips expose exactly one version | Packet 7 `version_overlap` |
| ACL/deletion suppress evidence; quarantine; rebuild/upgrade/rollback | Packet 7 sweep |
| Inspection depth/row/timeout | bound benchmarks |
| Throughput/rebuild proves **or reduces** seven-day envelope; fund reserve | **reduced** to 15 docs; reserve USD 800 floor |
| `SCALING_OPTIONS.md` trigger candidates | written, options only |
| Low-survival Hybrid handoff | `low_survival` + PHASE6_HANDOFF codes |
| Phase 6 frozen fixtures/interfaces; no holdout leakage; no Combined quality claim | PHASE6_HANDOFF + `P8-HOLDOUT` + `P8-COMBINED` deferred |

Phase status was `pending` until user acceptance. This packet did **not**
flip `05-phase-graphrag.md` by itself.

### Import-cycle deviation (required for freeze)

`packages/core/src/smart_rag_core/jobs/__init__.py` lazy-exports
`GraphWriterGuard` / `graph_advisory_lock_keys`. Eager import pulled
`retrieval.graph` during `evaluation` init and broke freeze (and Phase 4
freeze). Behavior of the writer is unchanged.

Contract `test_graph_retrieval.py` Packet 5 seed now uses
`load_extraction_policy()` so `mapping_config_generation` matches the
resolver (Packet 6 non-empty extraction hash). That alignment is a Packet 8
test fix, not a mapping-algorithm change.

### Commands and results

No commit, no push, no `uv sync --package smart-rag-core`. Holdout remains
sealed. Phase status remains `pending`. Combined/SSE/query-agent were not
implemented.

| Command | Exit |
| --- | --- |
| `uv run python scripts/eval_phase5_graph_freeze.py` | 0 (writes freeze + eval markdown) |
| `uv run python scripts/ci/check_migrations.py` | 0 (45 reviewed files) |
| `uv run python -m pytest tests/unit/test_phase3_graph_scope_guard.py tests/unit/test_lightrag_pin.py tests/unit/test_graph_mapping.py tests/unit/test_graph_resolver.py tests/unit/test_entity_rules.py tests/unit/test_graph_lifecycle.py tests/unit/test_graph_eval.py tests/unit/test_graph_retriever.py tests/contract/test_graph_mapping.py tests/contract/test_graph_retrieval.py tests/contract/test_entity_rules.py tests/contract/test_graph_lifecycle.py -q --durations=15` | 0 (109 passed) |
| `uv run python scripts/check.py --tier format` | 0 (416 files) |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (89 markdown files; Mermaid render) |

### Pre-existing non-blockers (not Packet 8 defects)

- Full-repo Pyright remains on the order of ~612 errors outside this packet.
- `tests/security/test_privileged_secrets_absent.py` still matches a
  `storage_admin` fragment (pre-existing).
- `tests/contract/test_graph_writer.py::test_graph_budget_kinds_are_isolated`
  failed locally with `budget_exhausted` (daily ingestion spend on the
  shared local DB). That node is **not** in the Packet 8 required pytest
  list.

### Deviations

- Live LightRAG extraction P/R is **unverified**; fixture CoverageSlice
  floors are not a substitute pass.
- GRAPH_MAPPING qualification rows are query labels, not extraction gold.
- Advertised envelope is **reduced** to 15 labeled `graph_mapping`
  documents; 2,000 / 200,000 is not claimed.
- Source-chunk capacity is **unverified**.
- Maintenance reserve uses the USD 800 floor because
  `4 x measured full-rebuild cost` cannot be evaluated.
- Combined +10pp is `deferred_phase_6`, not a Packet 8 pass.
- Lazy `jobs` graph-writer export (import cycle).
- Packet 5 retrieval contract seed aligned to Packet 6 extraction hash.

### Unverified

- Live corpus extraction precision/recall by language and type.
- Mapping-verified documents/hour on selected hardware.
- Graph source chunks/hour, queue age, cost/document, resource peaks.
- Full clean rebuild duration/cost of either 15 or 2,000 documents.
- Targeted deletion wall-clock within 24 hours on production hardware.
- Dirty consolidation wall-clock within seven days on production hardware.
- Snapshot restore of a production-sized LightRAG copy.
- Combined stream p95 / answer quality / holdout.
- Managed/staging apply of Packet 7 migration (already recorded).
- Full-repo Pyright and privileged-secret fragment (pre-existing).

### Rollback

- Do not advertise 2,000 / 200,000 until a measured rebuild exists.
- Keep bulk graph onboarding blocked (`P8-ENVELOPE` reduced).
- Disable the workspace or unset `LIGHTRAG_DB_URL` so query/inspection stay
  idle (`graph_outage`).
- Do not open holdout. Do not start Phase 6 Combined fusion from this packet.

### User-acceptance checklist (required before any Phase 5 status change)

Please confirm each item. **Do not** treat this file as acceptance.

1. Frozen manifest at `docs/graph/FROZEN_GRAPH_MANIFEST.md` is the signed
   pin (LightRAG 1.5.6, PGTable, hashes above).
2. Advertised graph envelope is **15 documents**, chunks **unverified**,
   bulk onboarding **blocked**; 2k/200k remains an aspiration only.
3. Maintenance reserve is **USD 800** until a measured rebuild cost exists;
   unfunded rebuild stays quarantined.
4. Live extraction P/R remains **unverified**; fixture language floors are
   accepted as infrastructure gates only.
5. Phase 6 handoff at `docs/graph/PHASE6_HANDOFF.md` is accepted, including
   the Combined quality **no-claim**.
6. Scaling options at `docs/graph/SCALING_OPTIONS.md` are options only;
   none are implemented.
7. Holdout stays sealed. Phase 5 `status` stays `pending` until you accept.
8. Production mapping Hybrid is wired through `bind_mapping_support` (in-memory
   version canonicals, one retrieve, one support rerank). Query-time Hybrid
   remains forbidden.

**Accepted 2026-08-16.** User confirmed the reduced close and asked to push
(`okay push`). Wrapper status is now `complete`. Holdout remains sealed.
Phase 6 owns Combined fusion, verifier/citations, holdout, and the +10pp
gain.

## Remaining Phase 5 — production mapping Hybrid wiring

### Quoted requirement

> Batch unresolved internal chunks and relation statements for that document
> into one scoped Hybrid RPC using chunk text plus entity/relation labels;
> retrieve only canonical chunks from that version, then apply one bounded
> support rerank through the same OpenAI-only `Reranker` gateway.

### Acceptance checks restated

- Worker mapping after vendor `processed` injects one version-scoped Hybrid
  retrieve and one OpenAI support rerank without naming map tables in `apps/`.
- Hybrid `ranked_ids` order/cap the support-rerank pool; empty or single
  ranked IDs skip rerank instead of scoring every canonical.
- Nested `asyncio.run` inside `process_claimed_job` does not fail.
- Gateway/prompt load failure returns `None` callbacks (hash/span/overlap
  still run; coverage fails closed).
- Repair still refuses attached Hybrid/rerank callbacks.

### Inspected files / pins

| Path | Role |
| --- | --- |
| `packages/core/src/smart_rag_core/jobs/graph_mapping_hybrid.py` | `bind_mapping_support`; in-memory Hybrid; OpenAI support rerank |
| `packages/core/src/smart_rag_core/jobs/graph_mapping_service.py` | Hybrid ranked_ids pool; `asyncio.to_thread` |
| `packages/core/src/smart_rag_core/jobs/graph_index_service.py` | Injects `mapping_support` into default mapper |
| `apps/worker/src/smart_rag_worker/graph_runner.py` | Calls `bind_mapping_support` |
| `packages/core/src/smart_rag_core/jobs/limits.py` | Candidate cap 100; support rerank deadline 8s |
| `docs/graph/MAPPING.md` | Production Hybrid wiring + sequence diagram |

### Commands and results

No push until user acceptance (recorded below). Holdout remains sealed. No
`uv sync --package smart-rag-core`. No new migration.

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/unit/test_graph_mapping.py tests/unit/test_graph_mapping_hybrid.py tests/unit/test_phase3_graph_scope_guard.py tests/contract/test_graph_mapping.py -q` | 0 (28 passed) |
| `uv run python -m pytest tests/unit/test_hybrid_run.py tests/unit/test_graph_mapping.py tests/unit/test_graph_mapping_hybrid.py tests/unit/test_phase3_graph_scope_guard.py tests/contract/test_graph_mapping.py -q` | 0 (46 passed) |
| `uv run python scripts/check.py --tier format` | 0 (418 files) |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 (89 markdown files; Mermaid render) |

### Deviations

- Mapping Hybrid uses in-memory version canonicals as dense/BM25/term channel
  jobs rather than live ParadeDB/pgvector RPCs. Canonical text is already
  loaded for hash/span/overlap; a second DB retrieve would `SET ROLE postgres`
  via Hybrid `_load_temporal_records` if `supabase_dsn` were passed.
- Combined fusion, SSE, query-agent, live extraction P/R, 2k-document rebuild,
  and holdout remain out of scope.

### Unverified

- Live OpenAI support rerank against a processed LightRAG corpus.
- Mapping-verified documents/hour and full-rebuild cost.
- Managed/staging apply of Phase 5 migrations (already recorded).
- Snapshot restore of a production-sized LightRAG copy into a second Postgres.

### Rollback

- Omit `mapping_support` (or let `bind_mapping_support` return `None`) so
  unresolved chunks stay unmapped and coverage fails closed.
- Unset `LIGHTRAG_DB_URL` to keep the graph adapter idle.

### Handoff

This closed the Packet 4 worker Hybrid hole. Combined fusion, SSE, and
query-agent remain Phase 6.

## Phase close

- Phase wrapper `status`: `complete` (`completed: 2026-08-16`).
- Accepted when the user said `okay push` after the reduced-envelope
  explanation in Cursor chat on 2026-08-16.
- Advertised envelope remains **15 documents**, chunks **unverified**, bulk
  graph onboarding **blocked**, maintenance reserve **USD 800**.
- Live extraction P/R remains unverified. Combined quality remains a Phase 6
  no-claim. Holdout stays sealed.
