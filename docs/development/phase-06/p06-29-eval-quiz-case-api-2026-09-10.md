---
title: P06-29 DB-backed pdf-eval case API
owner: engineering-lead
status: draft
last-reviewed: 2026-09-10
audience: engineering, reviewers, security
---

# P06-29 — Replace the HTTP file store with a typed DB-backed case API (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: replace HTTP `.private-eval/` construction with typed quiz RPC
wrappers. Local Compose defaults `PDF_EVAL_WORKSPACE_ENABLED` true. Python
settings default stays false so CI OpenAPI stays ungated. No exam runner.

User directed continuous execution through P06-36 on 2026-09-10.

## Plan requirement

Quote: replace the HTTP file store with a typed DB-backed case API.

Positive checks: owner/admin CRUD, CAS `row_version`, pagination, stale-gold,
regeneration, XSS-safe detail, list/status omit questions, members 403,
inaccessible IDs 404, disabled/staging/production routes absent, CLI store
tests still pass.

Negative checks: holdout rejected, payload bounds, forged member denied,
stale `row_version` 409, compare-run before completed owned run rejected,
missing migration 503 `quiz_schema_missing`, HTTP never falls back to
`.private-eval/`.

## Files

- [quiz_repository.py](../../../packages/core/src/smart_rag_core/evaluation/private_pdf/quiz_repository.py)
- [pdf_eval_workspace.py](../../../apps/backend/src/smart_rag_api/services/pdf_eval_workspace.py)
- [pdf_eval.py router](../../../apps/backend/src/smart_rag_api/routers/pdf_eval.py)
- [pdf_eval.py schemas](../../../apps/backend/src/smart_rag_api/schemas/pdf_eval.py)
- [test_pdf_eval_api.py](../../../tests/contract/test_pdf_eval_api.py)
- [test_eval_quiz_repository.py](../../../tests/unit/test_eval_quiz_repository.py)
- [docker-compose.yml](../../../docker-compose.yml) local default `true`
- [PDF_EVAL_WORKSPACE.md](../../evaluation/PDF_EVAL_WORKSPACE.md)
- [FASTAPI_SECURITY.md](../../api/FASTAPI_SECURITY.md)
- [AUTHORIZATION_MODEL.md](../../security/AUTHORIZATION_MODEL.md)
- [CONFIGURATION.md](../CONFIGURATION.md)

CLI [workspace_store.py](../../../packages/core/src/smart_rag_core/evaluation/private_pdf/workspace_store.py)
is unchanged. Frontend `expected_revision` stays until P06-34.

## Hosted passages RPC

Repo SQL [20260910140000_list_authorized_eval_passages_v1.sql](../../../supabase/migrations/20260910140000_list_authorized_eval_passages_v1.sql)
was missing on hosted project `qsjivtwtmlmtksufqjik`. Applied via MCP as
`list_authorized_eval_passages_v1`. Privilege proof (no private rows):

| Check | Result |
| --- | --- |
| `to_regprocedure(...list_authorized_eval_passages...)` | present |
| `app_api` EXECUTE | true |
| `anon` / `authenticated` EXECUTE | false |
| live `eval_quiz_cases` count | 0 |

`holdout_opened=false`. Staging/production eval UI stays off. Rollback is
`PDF_EVAL_WORKSPACE_ENABLED=false`.

## OpenAPI

Gated `/admin/pdf-eval/*` paths stay out of the foundation allowlist.
`scripts/ci/check_openapi.py` constructs the app with the Python default
false. The snapshot gained additive `/api/meta` field
`pdf_eval_workspace` (default false). No exam or pdf-eval case paths were
added.

## Verification

| Command | Exit |
| --- | --- |
| `uv run ruff check` on P06-29 Python | 0 |
| `uv run pyright` on P06-29 Python | 0 |
| `uv run pytest tests/contract/test_pdf_eval_api.py tests/unit/test_eval_quiz_repository.py tests/unit/test_pdf_eval_workspace_store.py tests/unit/test_settings.py -q` | 0 |
| `uv run python scripts/ci/check_openapi.py` | 0 after committing additive `/api/meta` `pdf_eval_workspace` |

## Proven

- HTTP service constructs `QuizCaseRepository` / fakes, never
  `PdfEvalWorkspaceStore`.
- Status is aggregate DB counts plus `holdout_opened=false`; no filesystem
  paths.
- Create from `source_run_id` only; extra `question` is 422.
- Missing schema is 503 `quiz_schema_missing`, not an empty workspace.
- Local Compose interpolates `PDF_EVAL_WORKSPACE_ENABLED:-true`. Python
  default remains false. Staging Compose does not interpolate true.
- Hosted passages RPC is present for later regenerate/passage lookup.

## Unverified

- Live HTTP create against hosted quiz RPCs (contract tests use an in-memory
  fake; ADR-cloud-only refuses hosted destructive pytest).
- Live regenerate against a current hosted document version.
- Frontend still sends `expected_revision` until P06-34.

## Handoff

Next packet is
[P06-30](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/30-eval-exam-database.md)
(exam runs/results/reports plus hidden evaluation conversations). Do not add
exam start HTTP in that packet. Do not start P06-11 until P06-30 through
P06-36 close.
