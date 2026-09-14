---
title: P06-36 Hosted evaluation workspace close
owner: engineering-lead
status: draft
last-reviewed: 2026-09-13
audience: engineering, reviewers, security, frontend
---

# P06-36 — Run integrated verification, reconcile docs, and write the close evidence (2026-09-13)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: run integrated verification, reconcile docs, and write the
close evidence.

Git SHA at this record: `54fbcdb` (working tree also contains this packet).
`holdout_opened=false` on hosted `eval_exam_reports_holdout_chk`.

Quote: run integrated verification, reconcile docs, and write the close
evidence.

## Plan requirement

Positive checks: repository commands with recorded exit codes; hosted
migration/project verification without secrets, or an explicit blocker;
live exam metric/hashes only when a live exam ran; `holdout_opened=false`;
rollback documented.

Negative checks: skipped required gates are not reported as pass; private
canary data in logs/traces/reports/errors fails the packet.

## Rollback

Set `PDF_EVAL_WORKSPACE_ENABLED=false`. Do not down-migrate populated hosted
quiz or exam tables. Ordinary Ask and thumbs feedback continue.

## Hosted catalog (project `qsjivtwtmlmtksufqjik`, no secrets)

Hosted history uses sliced MCP names. Repo files remain
`20260910150000_eval_quiz_cases_v1.sql`,
`20260910160000_eval_exam_runs_v1.sql`,
`20260913170000_eval_exam_report_read_v1.sql`. Hosted versions present:
`eval_quiz_cases_*`, `eval_exam_*`, `eval_exam_report_read_v1`.

| Check | Result |
| --- | --- |
| Quiz/exam tables | present |
| FORCE RLS quiz cases / exam runs | true / true |
| `app_api` INSERT/SELECT on quiz and exam tables | false |
| `anon`/`authenticated` quiz INSERT | false |
| `app_api` EXECUTE create/enqueue/latest/list/claim | true |
| `anon`/`authenticated` EXECUTE those RPCs | false |
| Helper `_eval_quiz_require_owner_admin` EXECUTE | false for api/anon/authed |
| SECURITY DEFINER `search_path` on sampled RPCs | set |
| Live `eval_quiz_cases` / `eval_exam_runs` counts | 0 / 0 |
| `eval_exam_reports_holdout_chk` | `CHECK ((holdout_opened IS FALSE))` |

Security advisors still list pre-existing `rls_enabled_no_policy` on
non-eval tables, mutable `search_path` on `app.estimate_llm_usage_cost_usd`,
GraphQL visibility of `app.run_events`, and Auth leaked-password protection
disabled. Eval tables were not in that advisor list. Region/DPA/backup
matrix rows stay **unverified** (P06-27 residual-risk exception).

## Verification

| Command | Exit |
| --- | --- |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update` | 0 (192 canonical files) |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | 0 (192 canonical files) |
| `uv run python scripts/ci/check_migrations.py` | 0 (83 files; sha256 `1f357e03f433297e3c4d263ba98a40da8c6b578824dd935a370c377fa3be643b`) |
| `uv run python scripts/check_docs.py` | 0 |
| `pnpm exec markdownlint-cli2 docs/**/*.md` | 0 (256 files) |
| `uv run python scripts/check_frontend_action_inventory.py` | 0 |
| `uv run ruff check` (eval runner/API/supervisor/tests) | 0 |
| `uv run pyright` (eval runner/API/supervisor) | 0 |
| `uv run pytest` quiz/exam DB, HTTP, runner, supervisor, quiz repo, settings | 0; **69 passed, 11 skipped** |
| `pnpm test --` evaluation, pdf-eval, eval-workspace | 0; 40 passed |
| `pnpm test --` administration-surfaces, save-to-quiz, chat-app | 0; 58 passed |
| `pnpm typecheck` / `lint` / `build` | 0 |
| `pnpm exec playwright test tests/e2e/administration-surfaces.spec.ts` | 0; 1 passed; live owner/member skipped |

The 11 skipped pytest cases need `SUPABASE_DB_URL` (ADR-cloud-only). They
are **not** recorded as pass. Destructive hosted pytest was not run.

## Passed

- Plan integrity, migration allowlist/hash, Markdown links/Mermaid, markdownlint, action inventory.
- Owner/admin vs member HTTP 403, disabled 404, staging Compose must not default the eval flag on, holdout body enum rejected, empty dataset 422 counts, one-active and qualification-consumed 409 (HTTP fakes).
- Runner unit: ranked-ID parity + `cold_bypass`, no version pin, crash resume, BM25 `gates_pass=false`, cancel/budget true-up, stale gold, qualification fingerprint fail-closed, lease reclaim, content-free error codes.
- Frontend scoreboard headline **All required gold chunks in the production Hybrid top 10**; citation overlap stays **not Recall@10**; XSS/RTL curation; members have no Evaluation tab in chrome specs.
- Docs reconciled: both evaluation ADRs, PDF eval workspace/hybrid, ADMINISTRATION, API_UI_MAPPING, FASTAPI_SECURITY, AUTHORIZATION_MODEL, CONFIGURATION, data dictionary, QUALITY_TARGETS (metric distinction already recorded), action inventory, docs index. SUBPROCESSOR matrix **not** marked verified.

## Blocked (not pass)

- Live SQL mutation/IDOR/capacity/purge against hosted Postgres (`SUPABASE_DB_URL` unset; hosted destructive pytest forbidden).
- Live exam enqueue + supervisor scoring on production Hybrid. Hosted exam_run_count is 0. **Do not treat mocks as live Recall@10.** No metric version, hashes, numerator/denominator, or degradation from a live exam.
- Live owner Playwright (E2E_LIVE_EMAIL/PASSWORD unset in this run).
- Managed region/DPA/backup/subprocessor verification.

## Failed

None in the commands that ran.

## Not run

- Full `scripts/check.py --tier unit|contract|fast` (pre-existing non-eval failures exist in historical P06-15; this packet scoped eval + docs gates).
- Staging/production deployed API process (settings tests prove the flag is rejected at load).

## Handoff

This overlay is ready for **user acceptance**. After acceptance, resume
[P06-11](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/11-sse-stream-lifecycle-tracing.md)
(SSE stream lifecycle and LangSmith tracing). Do not start P06-11 until the
user accepts this close. Do not freeze Hybrid or open holdout from this
workspace.
