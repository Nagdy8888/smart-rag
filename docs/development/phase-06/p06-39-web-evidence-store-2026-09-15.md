---
title: P06-39 run-scoped web evidence store
owner: engineering-lead
status: draft
last-reviewed: 2026-09-15
audience: engineering, reviewers, security
---

# P06-39 — Run-scoped web evidence store (2026-09-15)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

## Plan requirement

Quote: add durable run-scoped web evidence, URL citations, and merged
`source_kind` listing.

Positive checks: owned insert/list; same key+hash replays; different hash
conflicts; seventh source, thirteenth citation, cross-run source, bad URL,
bad hash, oversized excerpt, and non-contained span fail closed; merged
API returns `source_kind` and no evidence body; company ACL stripping
unchanged in v3 company branch; deletion purges all three tables.

Negative checks: direct `app_api` table INSERT fails; listing never
returns excerpt, span, query, or HTML keys; v2 company list RPC remains.

## Files

- [supabase/migrations/20260914120000_web_research_evidence_v1.sql](../../../supabase/migrations/20260914120000_web_research_evidence_v1.sql)
- [scripts/ci/check_migrations.py](../../../scripts/ci/check_migrations.py)
- [docs/deployment/phase-10/packet2-migration-hash.json](../../deployment/phase-10/packet2-migration-hash.json)
- [packages/core/src/smart_rag_core/web_research/](../../../packages/core/src/smart_rag_core/web_research/)
- [08-data-dictionary.md](../../architecture/08-data-dictionary.md)
- [AUTHORIZATION_MODEL.md](../../security/AUTHORIZATION_MODEL.md)

## Hosted apply (no secrets, no private rows)

Canonical SQL remains one repo file. Hosted history records sliced MCP
names because a single payload is easier to review. Behavior matches the
repo file after the slices below.

| Slice | Result |
| --- | --- |
| `web_research_evidence_tables_rls_v1` | success |
| `web_research_ops_rpcs_v1` | success |
| `web_research_insert_source_citation_v1` | success |
| `list_run_citations_v3` | success |
| `web_research_rpc_grants_v1` | success |
| `web_research_lingering_ids_v1` | success |
| `delete_conversation_web_evidence_v1` | success |

Privileges proven on project `qsjivtwtmlmtksufqjik` via catalog queries:

| Check | Result |
| --- | --- |
| `to_regclass` for the three Web tables | present |
| FORCE RLS on operations/sources/citations | true |
| Live row counts | 0 / 0 / 0 |
| `app_api` / `anon` / `authenticated` table DML grants | none |
| Public Web RPCs EXECUTE for `app_api` | true |
| Public Web RPCs EXECUTE for `anon` / `authenticated` | false |
| Helper `_web_require_run_owner` EXECUTE for `app_api` | false |
| `app_worker` EXECUTE on insert/list RPCs | false |
| `app.list_run_citations_v2` still EXECUTE for `app_api` | true |

Body-omitted listing contract (unit): `CitationResponse` schema has
`source_kind` / `web_source_id` and no `excerpt` / `span` / `html`.
SSE `citation_preview` uses `web_source_id` values and never span text.

## Verification

| Command | Exit |
| --- | --- |
| `uv run python scripts/ci/check_migrations.py` | 0 (84 files; sha256 `d33b20bba6b9f8ae14ea9052390fc25281d5a876b2a3bd7e019760fd6849c057`) |
| `uv run python -m pytest tests/unit/test_web_citations.py -q` | 0 (10 passed) |
| `uv run python -m ruff check` on web_research, citations, query_runs, SSE mapping, tests | 0 |
| `uv run python -m pyright` on web_research, citations, query_runs, SSE mapping | 0 |
| `uv run python -m pytest tests/contract/test_web_citation_persist.py tests/contract/test_citation_acl_recheck.py -q` | skipped (`SUPABASE_DB_URL` unset; [ADR-cloud-only-supabase-no-local-fixture.md](../../adr/ADR-cloud-only-supabase-no-local-fixture.md)) |

## Proven

- Python URL policy rejects loopback and userinfo.
- Span containment and SHA-256 hashing fail closed in core.
- HTTP sanitizer preserves `source_kind` and `web_source_id`.
- Hosted tables exist with FORCE RLS and no `app_api` table DML.
- Hosted RPCs are `app_api` EXECUTE only; the owner helper is not granted.

## Unverified

- Mutation/IDOR/cap tests against a non-hosted `SUPABASE_DB_URL`.
- `supabase gen types --project-id` (CLI not installed). `database.ts`
  was patched UTF-8 to add the three tables and Web RPCs, including
  `list_run_citations_v3`.

## Rollback

Do not down-migrate populated tables. Disable Web at settings
(`WEB_SEARCH_ENABLED=false`). Listing v2 remains for company rows.

## Handoff

Next packet is P06-40 four-mode admission and Web envelope. Store API:
`begin_web_research_operation`, `mark_web_research_operation_sent`,
`complete_web_research_operation`, `insert_web_source`,
`insert_web_citation`, `persist_web_answer_citations`,
`list_run_citations` (v3).
