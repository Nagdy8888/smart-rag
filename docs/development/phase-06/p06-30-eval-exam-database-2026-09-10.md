---
title: P06-30 durable exam-run schema and hidden evaluation conversations
owner: engineering-lead
status: draft
last-reviewed: 2026-09-10
audience: engineering, reviewers, security
---

# P06-30 — Add durable exam-run, result, report, and hidden-conversation database contracts (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: add exam-run, count-only result, immutable report, and hidden
evaluation-conversation database contracts. No FastAPI exam routes.

User directed continuous execution through P06-36 on 2026-09-10.

## Plan requirement

Quote: add durable exam-run, result, report, and hidden-conversation
database contracts.

Positive checks: one queued/running exam, qualification-once after any
persisted result, 365-day expiry, `metric_version=production_corpus_all_required_gold_at_10_v1`,
`cache_mode=cold_bypass`, `holdout_opened` CHECK false, hidden `purpose=evaluation`
conversations, immutable successful reports, idempotent case results.

Negative checks: holdout rejected, stale dataset hash / stale gold /
unapproved or zero-gold rejected at enqueue, live lease not reclaimable,
duplicate result cannot double-increment, no questions/answers/excerpts/
ranked IDs/gold UUID lists in result or report tables, no `app_worker`
SELECT on conversations, no table DML for runtime roles.

## Files

- [supabase/migrations/20260910160000_eval_exam_runs_v1.sql](../../../supabase/migrations/20260910160000_eval_exam_runs_v1.sql)
- [tests/contract/test_eval_exam_database.py](../../../tests/contract/test_eval_exam_database.py)
- [scripts/ci/check_migrations.py](../../../scripts/ci/check_migrations.py) allowlist
- [docs/deployment/phase-10/packet2-migration-hash.json](../../deployment/phase-10/packet2-migration-hash.json)
- [08-data-dictionary.md](../../architecture/08-data-dictionary.md)
- [AUTHORIZATION_MODEL.md](../../security/AUTHORIZATION_MODEL.md)
- [PDF_EVAL_WORKSPACE.md](../../evaluation/PDF_EVAL_WORKSPACE.md)

## Hosted apply (no secrets, no private rows)

Canonical SQL remains one repo file. Hosted history records sliced MCP
names because a single ~41KB payload exceeded the apply tool. Behavior
matches the repo file.

Privileges proven on project `qsjivtwtmlmtksufqjik` via catalog queries:

| Check | Result |
| --- | --- |
| `to_regclass` exam tables | present |
| `conversations.purpose` | present |
| FORCE RLS on exam tables | true |
| `app_api`/`app_worker`/`anon`/`authenticated` table DML | none |
| Public exam RPCs EXECUTE for `app_api` | true |
| Public exam RPCs EXECUTE for `anon`/`authenticated` | false |
| Helper `_eval_exam_*` and protect trigger EXECUTE for `app_api` | false |
| SECURITY DEFINER `search_path` on enqueue | `pg_catalog, app, extensions` |
| SECURITY DEFINER `search_path` on claim / conversation RPCs | `pg_catalog, app` |
| `app_worker` SELECT on `conversations` | none |
| Live exam/result/report counts | 0 / 0 / 0 |
| `eval_exam_reports_holdout_chk` | `CHECK ((holdout_opened IS FALSE))` |

Sliced hosted names: `eval_exam_tables_rls_v1`,
`eval_exam_helpers_snapshot_v1`, `eval_exam_enqueue_v1`,
`eval_exam_claim_lease_v1`, `eval_exam_result_finalize_cancel_v1`,
`eval_exam_get_purge_v1`, `eval_exam_conversation_hide_v1`,
`eval_exam_conversation_messages_title_v1`, `eval_exam_grants_v1`.

`holdout_opened=false`. Staging/production eval UI stays off. Rollback is
`PDF_EVAL_WORKSPACE_ENABLED=false`. Do not down-migrate populated tables.

## Verification

| Command | Exit |
| --- | --- |
| `uv run python scripts/ci/check_migrations.py` | 0 (82 files; sha256 `d7a5f5268f5c0a5bbe76c14e8a2436cb1e66b1bc907b95afe033e20799948a96`) |
| `uv run pytest tests/contract/test_eval_exam_database.py -q` | 0; 6 passed, 1 skipped (`SUPABASE_DB_URL` unset; ADR-cloud-only) |

Live concurrency, qualification-once after provider call, IDOR, and
lease-reclaim mutation tests remain opt-in against a non-hosted
`SUPABASE_DB_URL` ([ADR-cloud-only-supabase-no-local-fixture.md](../../adr/ADR-cloud-only-supabase-no-local-fixture.md)).
They were not run against hosted Postgres.

## Proven

- Result and report tables store counts only (`hit`, `gold_count`,
  `ranked_hit_count`, `latency_ms`, `hit_count`, `hybrid_recall_at_10`).
- Browser create always inserts `purpose='chat'`. List/get/messages/title
  hide `purpose='evaluation'` without changing request schemas.
- `admit_query_run` was not changed; exam runner may admit on evaluation
  conversations in P06-31.
- Successful reports cannot UPDATE; DELETE requires
  `SET LOCAL app.eval_exam_purge='1'`.
- Duplicate case results use `ON CONFLICT DO NOTHING` and increment
  `completed_case_count` only on insert.

## Unverified

- Live two-client enqueue creating only one active exam.
- Live qualification-once after a persisted result (pytest skipped).
- Live browser RPC hide of an evaluation conversation (static SQL proven).
- Managed region/DPA/backup matrix rows. Residual-risk exception from
  P06-27 still applies.

## Handoff

Next packet is
[P06-31](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/31-eval-exam-runner.md)
(restart-safe production-corpus Hybrid exam runner; no HTTP start/poll).
Do not start P06-11 until P06-28 through P06-36 close.
