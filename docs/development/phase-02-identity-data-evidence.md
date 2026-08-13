---
title: Phase 2 identity/data evidence
owner: engineering-lead
status: accepted
last-reviewed: 2026-08-13
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

### Audit-clean deterministic re-verification — 2026-08-13

The reopened Packet 2 used workspace-pinned Supabase CLI 2.114.0. Current
[Supabase local workflow documentation](https://supabase.com/docs/guides/local-development/cli-workflows)
confirms that `db reset` recreates the local database from ordered migrations
and that `gen types --local` is the canonical local type-generation path.

New proof artifacts:

- `scripts/ci/schema_fingerprint.py` captures ordered application-role,
  extension, relation, column, constraint, enum, and browser/private-schema
  privilege inventories.
- `scripts/ci/check_schema_determinism.py` performs exactly two explicit
  `db reset --local --yes` passes, runs `test_schema_reset.py` after each,
  generates types in memory, and compares both passes plus the committed type
  artifact.
- `test_migration_policy.py` proves destructive DDL, managed-Supabase
  `pg_search`, and an unsafe `SECURITY DEFINER` function fail migration policy.
  No migration or reviewed-prefix allowlist change was needed.

```text
uv run python scripts/ci/check_schema_determinism.py
→ reset 1 schema SHA-256 13d46a8e89426cbcaa1883c7af62940f980548ada5cc2c352be1f746d503aebd
→ reset 2 schema SHA-256 13d46a8e89426cbcaa1883c7af62940f980548ada5cc2c352be1f746d503aebd
→ both type SHA-256 c4206f32614946490785424e20ae612cb87049832017471486719d5a16edb5d1
→ each pass: 5 roles, 9 extensions, 86 relations, 778 columns,
  268 constraints, 90 enum labels, 8 private-schema browser-denial rows
→ passed; exit 0

uv run pytest tests/unit/test_migration_policy.py \
             tests/contract/test_schema_reset.py -q
→ 9 passed; exit 0

uv run python scripts/ci/check_migrations.py
→ Phase 2 migration policy OK (17 reviewed files); exit 0
```

The first attempt failed before resetting because the previously generated
`database.ts` used UTF-16 PowerShell redirection. It was regenerated directly
from the pinned CLI as UTF-8; the successful gate proves byte-stable normalized
output against both clean databases. Packet 2 has no remaining blocker.
LightRAG vendor-owned table DDL and HNSW creation remain assigned to their
explicit later phases; this packet proves only the reviewed Phase 2 private
schema capture boundary.

### Next packet

Packet 3 — least-privilege roles, RLS, ACL, and identity propagation.

## Packet 3 — least-privilege roles, RLS, ACL, identity propagation

### Requirement

Create runtime roles (`app_api`, `app_worker`, `app_checkpointer`, `app_lightrag`, `app_audit_writer`), RLS policies, ACL semantics, authorization-version triggers, security-invoker RPCs, core `CallerContext`, FastAPI identity stub, RLS matrix tests, and security docs.

### Artifacts

| Area | Path |
| --- | --- |
| Migrations | `20260812135916_roles_rls_identity_v1.sql`; `20260813110152_authorization_acl_pool_safety_v1.sql` |
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
- Production Supavisor concurrency/load remains Phase 9; local physical
  connection reuse is now proven.
- Storage RLS deferred to Packet 5.

### Audit-clean authorization re-verification — 2026-08-13

The reopened matrix found one real production-boundary gap: owner/admin ACL
policies existed, but browser roles were intentionally revoked and `app_api`
had no approved mutation RPC. The forward migration created through Supabase
CLI adds `private.set_document_acl`; it validates live typed caller context,
serializes by document row, permits only owner/admin, is idempotent, writes
grant/revoke audit events, and grants only `EXECUTE` to `app_api`.

```text
pnpm exec supabase db reset --local --yes
→ Applied 18 ordered migrations including authorization_acl_pool_safety_v1; exit 0

uv run python scripts/ci/check_migrations.py
→ Phase 2 migration policy OK (18 reviewed files); exit 0

uv run pytest tests/contract/test_rls_matrix.py -q
→ 7 passed; exit 0

uv run ruff check tests/contract/test_rls_matrix.py
uv run pyright tests/contract/test_rls_matrix.py
→ clean; 0 errors / 0 warnings
```

The matrix now proves:

- owner/admin read all active documents and may grant/revoke restricted ACL;
  member, upload-capable member, viewer, and disabled contexts cannot mutate it;
- members/viewers read company-visible documents, restricted grants are
  explicit, disabled/missing/forged/elevated/stale contexts return zero rows;
- conversations remain creator-private while owner/admin audit reads work;
- ACL mutations bump authorization generation, invalidate stale snapshots, are
  idempotent, and create content-free append-only audit events;
- only current company-visible graph-eligible versions pass; a restricted
  downgrade clears eligibility and emits a high-priority `graph_acl_remove`;
- one physical connection reused across committed transactions retains a
  deliberately malicious user-A `request.jwt.claims` GUC, yet a user-B RPC call
  is governed only by user-B typed arguments and cannot see user-A evidence;
- all five application roles are non-login, non-superuser, non-BYPASSRLS, and
  checkpointer/LightRAG roles cannot cross into canonical `app` tables.

The local reuse proof does not claim managed Supavisor load behavior; that
remains Phase 9. The new forward migration has not been applied remotely because
this closeout permits read-only managed verification only.

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

### Audit-clean Auth lifecycle re-verification — 2026-08-13

Current Supabase primary documentation was rechecked before remediation:

- [MFA](https://supabase.com/docs/guides/auth/auth-mfa) confirms verified
  factors and AAL2 enforcement, and does not provide recovery codes.
- [Auth Admin factor deletion](https://supabase.com/docs/reference/javascript/auth-admin-deletefactor)
  confirms that deleting a verified factor logs out active sessions.
- Current GoTrue OpenAPI defines
  `GET /admin/users/{userId}/factors`,
  `DELETE /admin/users/{userId}/factors/{factorId}`, and global user logout.

The audit found and repaired two fail-open lifecycle defects. Invitation domain
policy was supplied by the caller rather than loaded from
`app.allowed_email_domains`. MFA recovery persisted `completed` before the Auth
Admin mutation, so provider failure could create false completion. The repaired
boundary now:

- resolves active invitation/recovery/offboarding actors from `app.profiles`;
- requires AAL2 for privileged recovery and offboarding;
- requires a distinct verified recovery actor and stores only a bounded external
  verification method/reference in append-only
  `app.mfa_recovery_verifications`;
- suspends upload/MFA capability and invalidates existing access tokens at
  initiation;
- deletes all factors and globally logs out the subject before committing
  recovery completion;
- revokes application invite tokens when provider delivery fails;
- applies Phase 2 offboarding security effects (disable, upload downgrade,
  session revocation, authorization bump, audit) while leaving export/purge to
  its later owner.

New proof artifacts:

- `20260813110914_auth_recovery_verification_v1.sql`
- `auth_admin/offboarding.py`
- `test_auth_lifecycle.py`
- `test_auth_admin_boundaries.py`

```text
pnpm exec supabase db reset --local --yes
uv run pytest -q tests/contract/test_auth_lifecycle.py \
  tests/contract/test_invitations_auth.py tests/contract/test_jwks_auth.py \
  tests/contract/test_auth_rate_limits.py
→ 20 passed; exit 0

uv run pytest -q tests/unit/test_auth_admin_boundaries.py \
  tests/contract/test_auth_lifecycle.py
→ 9 passed; exit 0

uv run pyright apps/backend/src/smart_rag_api/auth_admin \
  tests/contract/test_auth_lifecycle.py tests/unit/test_auth_admin_boundaries.py
→ 0 errors, 0 warnings; exit 0
```

The contracts prove authoritative invitation domains, delivery-failure
compensation, initiation/completion audit, append-only verification metadata,
distinct-actor/last-owner denial, provider-outage rollback, factor endpoint
ordering, all-session revocation, current-token rejection by `iat`, capability
downgrade, authorization-version bump, completed offboarding state, and deferred
purge labeling. The existing managed JWKS evidence was inspected only; no key
rotation or paid call was repeated.

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

### Audit-clean restricted-read, mail, and Storage re-verification — 2026-08-13

The reopened Packet 5 added one CLI-created forward migration,
`20260813112729_restricted_read_audit_v1.sql`. The
`app.authorize_restricted_read` RPC revalidates typed caller context, active
restricted visibility, current version, and ACL. It permits only `evidence`,
`preview`, or `download`; requires a future expiry for download; and atomically
appends a hash-chain row plus an immutable `restricted_read_events` row. Stored
metadata contains IDs, purpose, session, expiry, and access surface only—never
evidence text, preview content, raw URLs, tokens, or object bytes.

The pinned Supabase CLI 2.114.0 template and current config reference were
rechecked. Local mail now uses the current `[local_smtp]` key (the deprecated
`[inbucket]` key emitted a warning). Removing a stale legacy internal SMTP port
fixed real provider invitation failure against the current Mailpit-backed local
mail service. Google OAuth remains safely disabled without credentials, while
client ID/secret names are environment-backed, provider callback derivation is
explicit (`redirect_uri=""`), nonce/email behavior is explicit, and
post-authentication redirects are exact localhost callback URLs with no
wildcards. No live Google login is claimed.

Local integration proof covers:

- email/password signup, sign-in, and wrong-password rejection;
- a real Auth Admin invitation delivered through local SMTP, with the
  application invitation token bound in Auth user metadata;
- a metadata-only admin alert delivered through the same local SMTP channel;
- real bytes uploaded/read from `documents-quarantine`, deleted through the
  Storage HTTP API, absent on retry, and absent from `storage.objects`;
- explicit denial of direct Storage metadata deletion by `app_api` and
  `app_worker`;
- the original quota, cleanup retry, graph downgrade, bucket/RLS, scan
  foundation, notification, and audit-chain contracts.

The live deletion test exposed one current provider nuance: a missing Storage
object returns HTTP 400 with an inner `404` / `not_found` / `NoSuchKey`
envelope. The boundary now accepts only that exact envelope as idempotent;
arbitrary HTTP 400 remains a hard failure.

```text
uv run python scripts/ci/check_migrations.py
→ Phase 2 migration policy OK (20 reviewed files); exit 0

uv run pytest -q tests/contract/test_storage_buckets_rls.py \
  tests/contract/test_upload_quota.py tests/contract/test_quarantine_cleanup.py \
  tests/contract/test_graph_eligibility_storage.py \
  tests/contract/test_restricted_read_audit.py \
  tests/contract/test_storage_live_api.py \
  tests/contract/test_local_auth_mail.py tests/contract/test_audit_chain.py
→ 24 passed; exit 0
```

The first combined run also exposed an order-dependent audit test that assumed
an empty ledger. It now compares the first fixture event to the actual prior
chain head (or genesis when empty), preserving the same tamper assertions in
both isolated and suite order.

### Next packet

Packet 6 — connection isolation, protected credentials, audit integrity, and exit.

## Packet 6 — connection isolation, protected credentials, audit integrity, exit

### Requirement

Prove Supabase/ParadeDB connection budgets against Compose inventory; apply role
timeouts/work_mem/application_name; implement hash-chained audit with redaction
and tamper verification; document protected credential custody; regenerate types;
map every Phase 2 `Done when` item; **request user acceptance** without setting
phase wrapper `status: complete`.

### Artifacts

| Area | Path |
| --- | --- |
| Migration | `supabase/migrations/20260813150000_audit_chain_role_timeouts_v1.sql` (renamed from empty `20260813081133_*` stub) |
| Advisor remediation | `supabase/migrations/20260813160000_security_advisor_search_path_v1.sql` |
| Core helpers | `packages/core/src/smart_rag_core/security/audit_chain.py` |
| Schema model | `AuditEventRecord` hash/purpose/resource fields |
| Generated types | `packages/core/src/smart_rag_core/generated/database.ts` |
| Docs | `05`/`06`/`07` architecture; `PROTECTED_MIGRATION_CREDENTIALS.md`; `AUDIT_CHAIN.md` |
| Contracts | `test_connection_budgets.py`, `test_audit_chain.py`, `test_privileged_secrets_absent.py` |
| CI gates | `scripts/ci/check_migrations.py`, `scripts/ci/check_phase2_integration.py` |

### Connection math (proven inventory)

| Item | Value |
| --- | --- |
| Compose API / worker replicas | 1 / 1 (no `deploy.replicas`) |
| Caps | API txn 10 + sess 4+4 + worker txn 6 + sess 4 + ops 2 |
| Worst-case sum | **30** |
| Managed Free/Nano hard limit | **60** |
| 70% ceiling | **42** |
| Gate | **30 < 42** |

ParadeDB independent: reader 4 + writer 2 + ops 1 = 7; no host ports published.

### Commands and results

```text
npx supabase db reset --yes
→ Applied 17 migrations including 20260813150000_audit_chain_role_timeouts_v1.sql; exit 0

uv run python scripts/ci/check_migrations.py
→ Phase 2 migration policy OK (17 reviewed files); exit 0

uv run ruff check/format on Packet 6 Python paths
→ All checks passed; exit 0

uv run pytest tests/contract/test_connection_budgets.py \
             tests/contract/test_audit_chain.py \
             tests/contract/test_privileged_secrets_absent.py -q
→ 8 passed; exit 0

npx supabase gen types typescript --local --schema app,public,storage,auth
→ Wrote packages/core/src/smart_rag_core/generated/database.ts (includes audit_events.event_hash/chain_seq)

uv run pytest tests/contract/test_rls_matrix.py \
             tests/contract/test_schema_reset.py \
             tests/contract/test_compose_topology.py -q
→ passed after aligning RLS matrix graph-reject message match with Packet 5 assert text

uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update
→ Split plan integrity updated: 82 canonical files; exit 0
```

### Managed sync (2026-08-13)

Applied `audit_chain_role_timeouts_v1` to `qsjivtwtmlmtksufqjik` via MCP.
Verified `app_*` role timeout/`work_mem`/`application_name` settings,
`audit_events` chain columns, and `app.append_audit_event` / `app.verify_audit_chain`.

### Acceptance mapping (Packet 6)

| Check | Evidence |
| --- | --- |
| Worst-case < 70% with process multiplication + ops | `05-database-connections.md` + `test_connection_budgets.py` |
| Custom roles / no session-GUC identity leak | `validate_caller_context` source assert + SET ROLE app_api |
| Role timeouts/memory/tags introspected; pause triggers documented | `pg_roles.rolconfig` test + `06-database-workload-isolation.md` |
| ParadeDB independent budget + no public port | `07-bm25-projection.md` + Compose |
| Audit mutation/deletion/reorder detected; no writer update/delete; redaction | `test_audit_chain.py` |
| Privileged secrets absent from general runtime settings | `test_privileged_secrets_absent.py` |
| Managed custody | Documented as **Phase 10 unverified** in `PROTECTED_MIGRATION_CREDENTIALS.md` |
| Generated types match schema | `npx supabase gen types typescript --local` |

### Forbidden scope respected

No AWS Secrets Manager/OIDC/KMS/S3 Object Lock implementation, no read replicas,
no production pool changes, no load claims, no SES/on-call, no Phase 9/10 evidence
faking.

## Phase 2 exit record (accepted 2026-08-13)

**The user explicitly accepted this exit record on 2026-08-13.**

### Done when → evidence map

| Done when clause (summary) | Evidence | Managed limitation |
| --- | --- | --- |
| Local + managed pgvector 0.8+/iterative-scan | Packet 1 evidence + MCP managed gate | Managed selective HNSW via direct DSN optional |
| Arabic SQL/core/ParadeDB byte-identical | Packet 1 parity tests | — |
| ParadeDB BM25 contracts; no pg_search on Supabase | Packet 1 + Compose private | — |
| Embedding ADR + qualification report | Packet 1 ADR/report | Full-envelope RAM ≥16 GB before bulk embed |
| Expand/contract migrations, deterministic double reset, types | Packet 2 fingerprint/type gate + migration negative tests | — |
| Roles, RLS, ACL, identity RPCs, transaction-pool safe | Packets 3–6 | Supavisor mode on managed pooler Phase 9 |
| Asymmetric JWKS + managed rollover | Packet 4 managed proof | Local Auth cannot prove full lifecycle alone |
| Owner/invite/MFA/recovery/session revocation | Packet 4 | Hosted Auth throttle **not** proven locally |
| Auth Admin / Storage Admin isolated; no general runtime secrets | Packets 4–6 secret tests | Managed secret custody Phase 10 |
| Storage quotas, cleanup, graph eligibility, notifications | Packet 5 | ClamAV/promotion Phase 3 |
| Connection/ParadeDB budgets + isolation triggers | Packet 6 docs + tests | Production pool load Phase 9 |
| Audit-chain tamper detectable | Packet 6 `verify_audit_chain` | KMS/Object Lock anchoring Phase 10 |
| Protected migration credentials design | `PROTECTED_MIGRATION_CREDENTIALS.md` | OIDC/Secrets Manager **unverified** until Phase 10 |
| Generated types reviewed | Packet 6 regen | — |

### Unverified managed / deferred items (honest)

- AWS Secrets Manager + GitHub OIDC one-shot migration job
- KMS / S3 Object Lock audit anchoring
- Hosted Supabase Auth rate-limit enforcement proof
- Production Supavisor pool sizing under load (Phase 9)
- Read-replica candidate path (design only)
- SES / on-call alert routing

### Acceptance

The user explicitly accepted the Phase 2 exit record and its documented
managed-only limitations on 2026-08-13. The wrapper and canonical index may
therefore be marked complete. Phase 3 was not started in this run.

## Audit-clean Phase 1–2 closeout revalidation — 2026-08-13

### Passed

| Command or proof | Result |
| --- | --- |
| `uv run python scripts/check.py --tier fast --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 32 unit passed; 118 contract passed and six declared external tests skipped; docs, frontend lint/types/Vitest/build, and Playwright discovery passed |
| `uv run python scripts/ci/check_phase2_integration.py` | 102 mandatory local schema/RLS/Auth/Storage/audit/BM25 tests passed; **zero skipped** |
| `uv run python scripts/ci/check_schema_determinism.py` | Two clean resets produced schema SHA-256 `9098a7d9…030a` and type SHA-256 `e23b4985…abc6` both times |
| Plan integrity / migration / OpenAPI gates | 82 canonical files verified; 21 reviewed Phase 2 migrations passed; OpenAPI snapshot matched |
| `dev.ps1` then `verify-local.ps1` | Public endpoints healthy; all four private services unpublished; Valkey policies, `pg_search`, crawl denial, non-root UIDs, and mock-model profile passed |
| Dependency and secret scans | Python and Node: no known vulnerabilities; Gitleaks: 22 commits / about 2.17 MB / no leaks |
| Read-only managed inventory | Project `ACTIVE_HEALTHY`; Postgres 17.6.1.155; pgvector 0.8.2 installed; no managed `pg_search` |
| Existing paid embedding artifact | Raw JSON remains internally consistent: 33 documents, 22 queries, three candidates, and selected `text-embedding-3-large` at 1024 dimensions |
| Existing rollover artifact | Public JWKS currently exposes only the recorded active ES256 key `caa0e22b-…`; the revoked prior key is absent |

The dedicated integration gate starts/requires local Supabase and private
ParadeDB, runs only mandatory local checks, parses pytest's JUnit result, and
fails on any skip, failure, error, or zero-test collection. Managed pgvector and
JWKS postcondition tests are named explicitly as separate optional checks.

The managed security advisor reported a mutable search path on
`search.arabic_normalization_version()`. The forward-only
`20260813160000_security_advisor_search_path_v1.sql` migration pins it to
`pg_catalog`, and the mandatory local pgvector contract introspects that exact
setting. Advisor `rls_enabled_no_policy` information applies to intentional
deny-all backend-owned tables with direct browser grants revoked. No permissive
policy was added merely to silence an informational finding.

### Failed and repaired

- The first final Compose health probe failed because API/frontend services
  were stopped. The documented `dev.ps1` path started the stack; two later
  `verify-local.ps1` / mandatory integration runs passed.
- The managed advisor search-path warning was reproduced against the deployed
  schema and repaired forward-only in local canonical migrations as described
  above.

No failing local gate remains.

### Blocked

- **Explicit user acceptance remains required.** The Phase 2 wrapper and
  canonical index must remain pending until that response.
- The managed project contains the previously deployed baseline through
  `audit_chain_role_timeouts_v1`, but the four audit-closeout migrations for
  ACL pool safety, recovery verification, restricted-read admission, and the
  advisor search-path repair are not deployed. The selected scope was
  read-only managed verification, so no managed DDL was applied.
- Managed leaked-password protection is currently disabled. Enabling and
  proving that hosted Auth setting is an external control change, not a local
  code claim. Hosted Auth throttling also remains explicitly unproven.

### Not run

- The paid OpenAI embedding bake-off was not repeated; its raw artifact and
  accepted ADR were revalidated.
- Signing keys were not created, rotated, or revoked; the public JWKS
  postcondition was read without mutation.
- Optional direct managed-DSN pgvector execution, production Supavisor load,
  AWS OIDC/Secrets Manager, KMS/Object Lock, SES/on-call routing, and
  read-replica paths were not run. Their Phase 9/10 ownership is unchanged.

### Final acceptance

All mandatory local Phase 1–2 gates are green with zero skips in the dedicated
Phase 2 integration suite. The user explicitly accepted this record and its
managed-only limitations on 2026-08-13. Phase 2 is complete; Phase 3 did not
begin in this run.
