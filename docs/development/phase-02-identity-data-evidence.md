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

## Packet 3 — least-privilege roles, RLS, ACL, identity propagation

### Requirement

Create runtime roles (`app_api`, `app_worker`, `app_checkpointer`, `app_lightrag`, `app_audit_writer`), RLS policies, ACL semantics, authorization-version triggers, security-invoker RPCs, core `CallerContext`, FastAPI identity stub, RLS matrix tests, and security docs.

### Artifacts

| Area | Path |
| --- | --- |
| Migration | `supabase/migrations/20260812135916_roles_rls_identity_v1.sql` |
| Core identity | `packages/core/src/smart_rag_core/security/identity.py` |
| FastAPI stub | `apps/backend/src/smart_rag_api/dependencies/identity.py` |
| RLS tests | `tests/contract/test_rls_matrix.py` |
| Authorization model | `docs/security/AUTHORIZATION_MODEL.md` |
| Identity propagation | `docs/security/IDENTITY_PROPAGATION.md` |

### Commands and results

```text
npx supabase db reset --yes
→ Applied 14 migrations including 20260812135916_roles_rls_identity_v1.sql; exit 0

uv run python scripts/ci/check_migrations.py
→ Phase 2 migration policy OK (14 reviewed files); exit 0

uv run pytest tests/contract/test_rls_matrix.py tests/contract/test_schema_reset.py -q
→ 4 passed; exit 0
```

### Acceptance mapping

| Check | Evidence |
| --- | --- |
| Runtime roles created NOLOGIN | migration `CREATE ROLE` |
| anon/authenticated revoked on app tables | migration REVOKE + `test_browser_roles_denied_direct_app_access` |
| Forged/stale RPC context → zero rows | `test_rls_matrix_documents_conversations_and_audit` |
| Restricted doc hidden without ACL | same |
| Creator-private conversations | `list_user_conversations` RPC test |
| audit writer cannot UPDATE | trigger + `test_rls_matrix_*` |
| Visibility/ACL bumps authorization_version | `test_visibility_change_bumps_authorization_and_bm25_job` |
| Restricted graph job rejected | `test_rls_matrix_*` |
| No session GUC identity | `CallerContext` + RPC args; docs |
| SECURITY INVOKER RPCs fixed search_path | migration functions |

### Gaps / deferred

- Packet 4 JWKS verification replaces FastAPI header stub.
- authenticated RLS policies exist but grants remain revoked until Auth wiring.
- Supavisor concurrent pool reuse test deferred to Packet 6.
- Storage RLS deferred to Packet 5.

### Next packet

Packet 4 — asymmetric JWT/JWKS, PKCE Auth, invitations, MFA.

## Packet 4 — Auth, JWKS, MFA, invitations, rate-limit ownership

### Requirement

Asymmetric JWKS verification (no HS256/shared secret), Auth config (PKCE client-side,
password policy, Inbucket SMTP), invitations/bootstrap/MFA recovery via privileged
boundary, Postgres degraded rate limits, tests, ADR, runbooks.

### Artifacts

| Area | Path |
| --- | --- |
| ADR | `docs/adr/ADR-privileged-auth-administration-boundary.md` |
| JWKS verifier | `packages/core/src/smart_rag_core/security/jwks.py` |
| FastAPI identity | `apps/backend/src/smart_rag_api/dependencies/identity.py` |
| Privileged boundary | `apps/backend/src/smart_rag_api/auth_admin/` |
| Migration | `supabase/migrations/20260813120000_auth_jwks_invitations_v1.sql` |
| Auth config | `supabase/config.toml` |
| Rate ownership doc | `docs/security/AUTH_RATE_LIMIT_OWNERSHIP.md` |
| JWKS rollover runbook | `docs/runbooks/SUPABASE_JWKS_ROLLOVER.md` |
| Contract tests | `tests/contract/test_{jwks_auth,invitations_auth,auth_rate_limits,jwks_rollover}.py` |

### Commands and results

```text
npx supabase db reset --yes
→ Applied 15 migrations including 20260813120000_auth_jwks_invitations_v1.sql; exit 0

uv run python scripts/ci/check_migrations.py
→ Phase 2 migration policy OK (15 reviewed files); exit 0

uv run pytest tests/contract/test_jwks_auth.py tests/contract/test_invitations_auth.py \
             tests/contract/test_auth_rate_limits.py tests/contract/test_jwks_rollover.py -q
→ 15 passed, 1 skipped; exit 0

uv run ruff check/format on touched Python files
→ clean after fixes; exit 0
```

### Acceptance mapping

| Check | Evidence |
| --- | --- |
| No HS256/shared-secret verification path | `jwks.py` + `test_rejects_hs256_token_signed_with_local_jwt_secret` |
| iss/aud/alg/exp/sub/kid; cache ≤600s; one refresh | `JwksVerifier` + contract tests |
| Provider rollover | **PROVEN** on managed `qsjivtwtmlmtksufqjik` (standby→in_use→revoked); postcondition contract test |
| Owner bootstrap + invitations | migration RPCs + `test_invitations_auth.py` |
| MFA recovery privileged boundary | `auth_admin/mfa_recovery.py` + ADR |
| Auth Admin secret isolated | `PrivilegedAuthSettings` + secret scan test |
| Rate ownership documented | `AUTH_RATE_LIMIT_OWNERSHIP.md`; `local_auth_throttling_proven=False` |

### Managed Supabase sync (MCP, 2026-08-13)

Connected to account project `smart-rag` (`qsjivtwtmlmtksufqjik`) via
`plugin-supabase-supabase` MCP (same OAuth path used to create the project).

Applied Packet 2–4 schema migrations onto managed (Packet 1 already present):

- `app_schemas_enums_job_columns_v1` … `indexes_rls_grants_v1`
- `roles_rls_identity_v1` (history row + remainder via `execute_sql` after truncated
  first payload)
- `auth_jwks_invitations_v1`

Verified on managed: schemas `app`/`private`/`search`/`langgraph`/`lightrag`;
`app.team_invitations.upload_enabled`; `app.revoked_sessions`; roles `app_api` /
`app_worker` (`NOLOGIN`).

### Managed JWKS rollover proof (2026-08-13)

Using `SUPABASE_ACCESS_TOKEN` (gitignored `.env`) against Management API
`/v1/projects/qsjivtwtmlmtksufqjik/config/auth/signing-keys`:

| Step | Key id | Result |
| --- | --- | --- |
| Standby create | `caa0e22b-cd04-4ee8-9701-a75aa682da78` | ES256 `standby`; JWKS published both kids |
| Pre-rotate token | signed by `37b8d1b0-4217-4feb-becd-a986437dc994` | `JwksVerifier` OK |
| Rotate → `in_use` | `caa0e22b-…` | prior ES256 → `previously_used` |
| Post-rotate token | signed by `caa0e22b-…` | overlap: both tokens verify |
| Revoke prior | `37b8d1b0-…` → `revoked` | after edge JWKS drain (~10 min), old token fail-closed (`unknown kid after refresh`); new token still valid |

Final Management API state: `caa0e22b-…` `in_use` ES256; `37b8d1b0-…` `revoked` ES256; legacy HS256 remains `previously_used` (not in JWKS). Public JWKS kids: `caa0e22b-…` only.

Ops helper: `scripts/ops/prove_jwks_rollover.py` (destructive; do not run in CI). Contract gate:
`tests/contract/test_jwks_rollover.py` asserts durable postconditions when the token is present.

### Blockers / honest gates

- **Hosted Auth throttling not proven locally**: `local_auth_throttling_proven=False`.
- **PKCE**: enforced by Supabase client `flowType: 'pkce'` at frontend (Phase 8); local
  Auth stack supports PKCE flow per Supabase docs.
- Production retention before revoke should still honor `jwt_exp + app cache + edge cache`;
  this packet proved the lifecycle with an accelerated revoke after throttle windows.
- Restart local Supabase after `config.toml` Auth changes: `npx supabase stop && npx supabase start`.

### Next packet

Packet 5 — private Storage, quota capabilities, graph eligibility, retention.

## Packet 5 — private Storage, quotas, scan foundations, graph eligibility, retention

### Requirement

Private Storage buckets, upload quotas, quarantine cleanup, scan foundations,
graph eligibility, retention structures, admin notifications. ADR: user JWT +
Storage RLS INSERT (not signed upload URL); 15-minute admission;
effective capability `min(reservation_expires_at, access_token_exp)`;
privileged Storage Admin boundary for delete/list.

### Artifacts

| Area | Path |
| --- | --- |
| Migration | `supabase/migrations/20260813140000_storage_quotas_graph_retention_v1.sql` |
| ADR | `docs/adr/ADR-upload-capability-and-storage-privilege.md` |
| Storage Admin boundary | `apps/backend/src/smart_rag_api/storage_admin/` |
| Quota / cleanup services | `apps/backend/src/smart_rag_api/services/upload_quota.py`, `quarantine_cleanup.py` |
| Core model | `UploadQuotaReservationRecord` in `packages/core/.../schema/tables.py` |
| Docs | data dictionary Storage section; QUALITY_TARGETS QT-RET-*; docs index |
| Contract tests | `tests/contract/test_{storage_buckets_rls,upload_quota,quarantine_cleanup,graph_eligibility_storage}.py` |
| CI allowlist | `scripts/ci/check_migrations.py` |

### Commands and results

```text
npx supabase db reset --yes
→ Applied 16 migrations including 20260813140000_storage_quotas_graph_retention_v1.sql; exit 0

uv run python scripts/ci/check_migrations.py
→ Phase 2 migration policy OK (16 reviewed files); exit 0

uv run ruff check on Packet 5 Python paths
→ All checks passed; exit 0

uv run pytest tests/contract/test_storage_buckets_rls.py \
             tests/contract/test_upload_quota.py \
             tests/contract/test_quarantine_cleanup.py \
             tests/contract/test_graph_eligibility_storage.py -q
→ 13 passed; exit 0
```

### Managed sync (2026-08-13)

Applied `storage_quotas_graph_retention_v1` to `qsjivtwtmlmtksufqjik` via MCP
`apply_migration`. Verified five private buckets (`public=false`),
`upload_quota_reservations.idempotency_key`, and
`app.reserve_upload_quota` / `app.emit_admin_notification`.

### Acceptance mapping

| Check | Evidence |
| --- | --- |
| Private buckets; quarantine non-listable; own-path only | `test_storage_buckets_rls.py` |
| Effective capability truthful; ADR documents JWT vs 15m | ADR + `test_effective_capability_lifetime_label` |
| Declared/actual bytes, caps, expiry, over-limit, idempotent | `test_upload_quota.py`, `test_quarantine_cleanup.py` |
| Storage API delete (not SQL metadata delete); retry-safe | `storage_admin/objects.py` + `test_cleanup_uses_storage_api_not_sql_delete` |
| No fake clean scan without Phase 3 worker | `test_scan_events_block_fake_clean_for_app_api` |
| Restricted/non-current/deleted not graph eligible; ACL emits `graph_acl_remove` | `test_graph_eligibility_storage.py` |
| Admin notification fixtures + helper | `test_admin_notification_helper_and_fixtures` |
| Secret scan: Storage Admin secret not in SharedSettings | `test_shared_settings_reject_storage_admin_secret` |

### Forbidden scope respected

No ClamAV, MIME validation, promotion/parsing/OCR/embedding, crawling, graph
indexing execution, public buckets, or invented narrow service tokens.

### Next packet

Packet 6 — connection isolation, protected credentials, audit integrity, and exit.

