---
title: Phase 5 GraphRAG evidence
owner: engineering-lead
status: pending
last-reviewed: 2026-08-16
audience: engineering, reviewers
phase: 5
---

# Phase 5 — GraphRAG evidence

Canonical packet evidence and exit record for
[Phase 5](../../.cursor/plans/hybrid-graph-rag/05-phase-graphrag.md).
Packet 1 creates this file; later packets append. Phase status remains
`pending`. Holdout stays sealed. Packets 2–8 follow the identity-envelope
unblocker below.

Related: [LIGHTRAG_CONTRACT.md](../graph/LIGHTRAG_CONTRACT.md) ·
[ADR-graph-source-identity-envelope.md](../adr/ADR-graph-source-identity-envelope.md) ·
[ADR-lightrag-runtime-attach-without-ddl.md](../adr/ADR-lightrag-runtime-attach-without-ddl.md) ·
[ADAPTER_LIFECYCLE.md](../graph/ADAPTER_LIFECYCLE.md) ·
[ADR-lightrag-identical-content-collapse.md](../adr/ADR-lightrag-identical-content-collapse.md) ·
[TOOL_VERSIONS.md](./TOOL_VERSIONS.md) ·
[CONFIGURATION.md](./CONFIGURATION.md) ·
[ADR index](../adr/README.md) ·
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
