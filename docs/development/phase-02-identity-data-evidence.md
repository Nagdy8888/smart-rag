---
title: Phase 2 identity/data evidence
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering, reviewers
---

# Phase 2 — identity and data evidence

Canonical packet evidence. Packet 1 creates this file; later packets append.

## Packet 1 — capability and embedding qualification

### Requirement

Prove local + managed pgvector 0.8+/iterative-scan, pinned ParadeDB/`pg_search` BM25 contracts, byte-identical `arabic_norm_v1`, and live embedding bake-off; freeze disjoint qualification slice; accept embedding ADR.

### Versions recorded

| Component | Value |
| --- | --- |
| Supabase CLI | 2.113.0 (`npx`) |
| Local Supabase Postgres | 15.8 / pgvector **0.8.0** |
| Managed project | `smart-rag` / `qsjivtwtmlmtksufqjik` / `eu-central-1` / Postgres 17.6 / pgvector **0.8.2** |
| ParadeDB | digest `sha256:dca046b8a0ddd070c368d5254cbb7f596b3b7bc67bc2efa7c0fbe881087883bb` / PG 17.10 / `pg_search` 0.25.2 / vector 0.8.4 |
| OpenAI candidates | `text-embedding-3-small`@1536; `text-embedding-3-large`@1536; `text-embedding-3-large`@1024 |

Managed target is the **new** Smart RAG project (not the previous Reel project).

### Artifacts

- Migration: `supabase/migrations/20260812131227_pgvector_gate_and_arabic_norm_v1.sql`
- Core: `packages/core/src/smart_rag_core/text/arabic_normalize.py`
- ParadeDB SQL: `infra/paradedb/sql/arabic_norm_v1.sql`
- Fixtures: `tests/fixtures/arabic_normalization/`, `tests/fixtures/embedding_qualification/`
- Contracts: `tests/contract/test_{arabic_normalization_parity,pgvector_capabilities,paradedb_bm25,embedding_dimensions}.py`
- Bake-off: `scripts/embedding_qualification_bakeoff.py` → `docs/evaluation/embedding_qualification_raw.json`
- Docs: Arabic normalization, BM25 projection `07`, embedding ADR + report

### Commands and results

```text
npx supabase db reset --yes
→ Applied 20260812131227_pgvector_gate_and_arabic_norm_v1.sql (local vector 0.8.0)

Managed MCP apply_migration pgvector_gate_and_arabic_norm_v1
→ normalize('مَدْرَسَة')='مدرسه'; assert_pgvector_capabilities()='0.8.2'; iterative_scan ok

uv run pytest tests/contract/test_arabic_normalization_parity.py \
             tests/contract/test_pgvector_capabilities.py \
             tests/contract/test_paradedb_bm25.py \
             tests/contract/test_embedding_dimensions.py -q
→ passed (managed DB URL test skipped — no direct pooled password in env; MCP SQL proved managed gate)

MOCK_MODEL_MODE=false uv run python scripts/embedding_qualification_bakeoff.py
→ Wrote embedding_qualification_raw.json; winner large@1024 per ADR
```

### Acceptance mapping

| Check | Evidence |
| --- | --- |
| Local pgvector 0.8+ + iterative-scan + selective filter | Local migration gate + `test_pgvector_capabilities` |
| Managed pgvector 0.8+ + iterative-scan | MCP SQL on `qsjivtwtmlmtksufqjik` |
| Arabic byte-identical SQL/core/ParadeDB | `test_arabic_normalization_parity` (0 failures) |
| ParadeDB BM25 contracts | `test_paradedb_bm25` |
| Live three-candidate bake-off | raw JSON + report |
| ADR pins live API ids/dims | ADR accepted large@1024 |
| No bulk ingest / no pg_search on Supabase | Migration scope limited |

### Unverified / follow-ups

- Managed selective-filter HNSW via direct `psycopg` DSN (password not stored in repo `.env`); MCP proved GUC + normalize.
- Full-envelope RAM: ADR requires ≥16 GB usable DB RAM or `halfvec` before bulk embed.
- Packet checkbox remains unchecked until user **accept**.

### Next packet

Packet 2 — expand/contract-safe authoritative schema (after Packet 1 accept).

## Packet 2 — expand/contract-safe authoritative schema

### Requirement

Forward-only Supabase migrations for the full v1 authoritative schema, ParadeDB `bm25_chunks` projection DDL, expand/contract migration lint, schema contract tests, connection/isolation docs, data dictionary, and core Pydantic mirrors. RLS policies deferred to Packet 3.

### Artifacts

| Area | Path |
| --- | --- |
| Migrations (13 files) | `supabase/migrations/20260812135034_*` … `20260812135115_*` |
| ParadeDB projection | `infra/paradedb/migrations/20260812170000_bm25_projection.sql` |
| Data dictionary | `docs/architecture/08-data-dictionary.md` |
| Connection budgets | `docs/architecture/05-database-connections.md` |
| Workload isolation | `docs/architecture/06-database-workload-isolation.md` |
| Migration lint | `scripts/ci/check_migrations.py` |
| Schema contract tests | `tests/contract/test_schema_reset.py` |
| Domain models | `packages/core/src/smart_rag_core/schema/` |

### Migration files (ordered)

1. `20260812131227_pgvector_gate_and_arabic_norm_v1.sql` (Packet 1)
2. `20260812135034_app_schemas_enums_job_columns_v1.sql`
3. `20260812135038_profiles_company_invitations_v1.sql`
4. `20260812135041_documents_sources_acl_v1.sql`
5. `20260812135045_document_chunks_tables_search_v1.sql`
6. `20260812135049_durable_jobs_v1.sql`
7. `20260812135053_lightrag_maps_v1.sql`
8. `20260812135056_conversations_messages_runs_v1.sql`
9. `20260812135100_tools_catalog_v1.sql`
10. `20260812135104_llm_usage_budgets_v1.sql`
11. `20260812135107_audit_events_v1.sql`
12. `20260812135111_langgraph_lightrag_private_v1.sql`
13. `20260812135115_indexes_rls_grants_v1.sql`

### Commands and results

```text
uv run python scripts/ci/check_migrations.py
→ Phase 2 migration policy OK (13 reviewed files); exit 0

npx supabase db reset --yes
→ Applied all 13 migrations; exit 0

uv run pytest tests/contract/test_schema_reset.py -q
→ 1 passed; exit 0

npx supabase gen types typescript --local > packages/core/src/smart_rag_core/generated/database.ts
→ generated (includes app/langgraph/lightrag schemas)
```

### Acceptance mapping

| Check | Evidence |
| --- | --- |
| Every canonical object documented | `08-data-dictionary.md` |
| Expand/contract lint | `check_migrations.py` |
| Clean reset + invariants | `test_schema_reset.py` |
| `vector(1024)` on chunks | migration + contract test |
| Current-version cross-doc trigger | migration + contract test |
| Audit append-only | trigger + contract test |
| Graph eligibility CHECK | contract test |
| Job idempotency UNIQUE | contract test |
| RLS enabled, no policies yet | `indexes_rls_grants_v1.sql` |
| LangGraph checkpoints reviewed | `langgraph_lightrag_private_v1.sql` |
| LightRAG vendor DDL deferred | `lightrag.schema_capture_status` |
| ParadeDB projection only derived IDs | `20260812170000_bm25_projection.sql` |

### Blockers / deferred

- LightRAG vendor table DDL awaits Phase 5 pinned `initialize_storages()` capture (documented stub only).
- Runtime role grants and RLS policies: Packet 3.
- HNSW index on `document_chunks.embedding`: after RAM gate / Phase 3 ingest.
- Generated Supabase TypeScript types: produced by CLI after successful reset.

### Next packet

Packet 3 — least-privilege roles, RLS, ACL, and identity propagation.
