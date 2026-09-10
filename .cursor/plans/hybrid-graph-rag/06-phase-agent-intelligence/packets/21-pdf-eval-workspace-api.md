---
phase: 6
packet: 21
status: complete
title: "Implement the local-only owner/admin PDF evaluation API and passage lookup."
requirement_ids: [P06-21]
---

# Packet 21 — Implement the local-only owner/admin PDF evaluation API and passage lookup.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md).
Do not load frontend skills.

## Preconditions

- Packet 20 store and draft generation exist.
- Glossary owner/admin router pattern is inspectable.

## Allowed outputs

- `apps/backend/src/smart_rag_api/schemas/pdf_eval.py`
- `apps/backend/src/smart_rag_api/services/pdf_eval_workspace.py`
- `apps/backend/src/smart_rag_api/routers/pdf_eval.py`
- Additive settings, `/api/meta` capability, `main.py` registration,
  Compose bind mount, OpenAPI, `docs/evaluation/PDF_EVAL_WORKSPACE.md`,
  `docs/security/AUTHORIZATION_MODEL.md`, and `docs/development/CONFIGURATION.md`
- Optional one forward migration for authorized representative passage list
  if no existing RPC can enumerate the current PDF version
- `tests/contract/test_pdf_eval_api.py` and settings unit tests

## Forbidden outputs

- Frontend files.
- Operator/service-role DSN.
- Holdout endpoints.
- Staging/production enablement.
- Client-supplied reviewer identity or filesystem path.

## Ordered actions

1. Add `PDF_EVAL_WORKSPACE_ENABLED` default false and
   `PDF_EVAL_WORKSPACE_ROOT` default `/app/.private-eval`.
2. Fail closed when enabled in staging or production.
3. Register owner/admin routes only when enabled and `APP_ENV=local` or test.
4. Implement status, paginated cases, case detail, PATCH, approve, reject,
   draft regenerate, passage list, latest report, and compare-run.
5. Approve writes `reviewer=caller.user_id`. PATCH cannot set reviewer,
   approval, split, actor, or holdout access.
6. Passage list uses `app_api` ACL/current-version rules and
   `fetch_authorized_chunk_context` or a new bounded RPC.
7. `compare-run` verifies the run belongs to the caller and scores citation
   overlap in core code.
8. Apply existing auth-adjacent rate limits to mutations.

## Acceptance checks

- Member/viewer receive 403. Disabled mode discloses no dataset status.
- Stale revision returns 409. Holdout paths remain unreachable.
- OpenAPI documents list endpoints without bulk question fields.

## Negative tests

- Forged member token 403.
- Cross-document passage id omitted.
- Holdout split query rejected.
- Staging settings with the flag true fail startup.

## Stop routes

- Stop rather than use `SET ROLE postgres` in the API process.
- Do not add a holdout REST list.

## Required evidence

- Append contract/unit command/exit, OpenAPI check, and Packet 22 handoff.
