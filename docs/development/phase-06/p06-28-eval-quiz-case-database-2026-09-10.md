---
title: P06-28 hosted quiz-case schema and app_api RPCs
owner: engineering-lead
status: draft
last-reviewed: 2026-09-10
audience: engineering, reviewers, security
---

# P06-28 — Hosted quiz-case schema, gold rows, and app_api RPCs (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: add `app.eval_quiz_cases` and `app.eval_quiz_gold_chunks`,
owner/admin `app_api` SECURITY DEFINER RPCs, capacity/idempotency/CAS,
content-free audit, and hosted apply without secrets.

User directed continuous execution through P06-36 on 2026-09-10.

## Plan requirement

Quote: implement hosted quiz-case schema, gold rows, and app_api RPCs.

Positive checks: tables, 0–3 gold locators, create/list/get/patch/gold/
approve/reject/delete/count/purge RPCs, `app_api` has no table DML,
PUBLIC/anon/authenticated cannot execute, holdout rejected, capacity 60,
idempotency collision rejected, foreign run/inaccessible gold are
`eval_quiz:not_found`.

Negative checks: no FastAPI, no frontend, no exam tables, no Compose
default change, no operator DSN from FastAPI, no holdout, no `.private-eval/`
import, no question/answer/excerpt logs.

## Files

- [supabase/migrations/20260910150000_eval_quiz_cases_v1.sql](../../../supabase/migrations/20260910150000_eval_quiz_cases_v1.sql)
- [tests/contract/test_eval_quiz_database.py](../../../tests/contract/test_eval_quiz_database.py)
- [scripts/ci/check_migrations.py](../../../scripts/ci/check_migrations.py) allowlist
- [docs/deployment/phase-10/packet2-migration-hash.json](../../deployment/phase-10/packet2-migration-hash.json)
- [08-data-dictionary.md](../../architecture/08-data-dictionary.md)
- [AUTHORIZATION_MODEL.md](../../security/AUTHORIZATION_MODEL.md)
- [PDF_EVAL_WORKSPACE.md](../../evaluation/PDF_EVAL_WORKSPACE.md)

## Hosted apply (no secrets, no private rows)

Canonical SQL remains one repo file. Hosted history records sliced MCP
names because a single 39KB payload exceeded the apply tool. Behavior
matches the repo file after DROP/recreate of mismatched get/patch/gold
bodies.

Privileges proven on project `qsjivtwtmlmtksufqjik` via catalog queries:

| Check | Result |
| --- | --- |
| `to_regclass('app.eval_quiz_cases')` | present |
| `app_api` INSERT/UPDATE/DELETE/SELECT on quiz tables | false |
| `anon`/`authenticated` table DML | false |
| FORCE RLS on `eval_quiz_cases` | true |
| Public RPCs EXECUTE for `app_api` | true |
| Public RPCs EXECUTE for `anon`/`authenticated` | false |
| Helper `_eval_quiz_*` EXECUTE for `app_api` | false |
| SECURITY DEFINER `search_path` | set |
| Live case count / gold row count | 0 / 0 |

`holdout_opened=false`. Staging/production eval UI stays off. Rollback is
`PDF_EVAL_WORKSPACE_ENABLED=false`. Do not down-migrate populated tables.

## Verification

| Command | Exit |
| --- | --- |
| `uv run python scripts/ci/check_migrations.py` | 0 (81 files; sha256 `57575c47f8aeeda879266c07e3393822f15bc93ef3039168257528b8d49bf327`) |
| `uv run ruff check tests/contract/test_eval_quiz_database.py` | 0 |
| `uv run pytest tests/contract/test_eval_quiz_database.py -q` | 0; 10 skipped (`SUPABASE_DB_URL` unset; ADR-cloud-only) |

Mutation/IDOR/capacity tests remain opt-in against a non-hosted
`SUPABASE_DB_URL` ([ADR-cloud-only-supabase-no-local-fixture.md](../../adr/ADR-cloud-only-supabase-no-local-fixture.md)).
They were not run against hosted Postgres.

## Proven

- 60-case cap and 365-day expiry in schema plus create RPC.
- Gold locators are server-derived from current ACL-visible chunks.
- Create never self-approves.
- Patch/gold replace reset `review_status`, reviewer, and `reviewed_at`.
- Approve requires answer, source family, and one to three current gold
  chunks on one document/version.

## Unverified

- Live concurrent create of case 61 on a labelled non-hosted fixture.
- Live foreign-run IDOR at the SQL boundary (pytest skipped).
- Managed region/DPA/backup matrix rows. Residual-risk exception from
  P06-27 still applies.

## Handoff

Next packet is
[P06-29](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/29-eval-quiz-case-api.md)
(DB-backed pdf-eval HTTP; local Compose default true; no exam runner).
Do not start P06-11 until P06-28 through P06-36 close.
