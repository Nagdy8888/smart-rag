---
phase: 6
packet: 29
status: complete
title: "Replace the HTTP file store with a typed DB-backed case API."
requirement_ids: [P06-29]
---

# Packet 29 — Replace the HTTP file store with a typed DB-backed case API.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md),
[`implement-observability-evals`](../../../../../.cursor/skills/implement-observability-evals/SKILL.md).

Do not implement exam execution in this packet.

## Preconditions

- P06-28 schema and RPCs exist. Inspect
  `PdfEvalWorkspaceStore`, `PdfEvalWorkspaceService`,
  `apps/backend/src/smart_rag_api/routers/pdf_eval.py`, schemas, passage RPC,
  and repository conventions.

## Allowed outputs

- Typed hosted repository under the existing private-PDF evaluation package.
- DB-backed `PdfEvalWorkspaceService` construction for HTTP.
- Updated pdf-eval schemas/router for case/source routes in section 8 of the
  hosted-evaluation ADR/brief.
- Local Compose `PDF_EVAL_WORKSPACE_ENABLED` default true; staging/production
  remain false and fail closed.
- OpenAPI snapshot and API/security/configuration docs.

## Forbidden outputs

- Exam start/poll/cancel routes or exam runner.
- Operator/service-role DSN in FastAPI.
- Deleting the file store used by CLI/legacy callers.
- Accepting browser-supplied question text as create provenance.
- Staging/production route registration.

## Ordered actions

1. Add typed repository records and one wrapper per reviewed SQL RPC.
2. Remove the file-store dependency from HTTP service construction. Keep
   the old store for CLI/legacy callers.
3. Implement case/source HTTP:
   `GET /status`, `POST /cases`, `GET /cases`, `GET /cases/{id}`,
   `PATCH /cases/{id}`, `PUT /cases/{id}/gold`, approve, reject, delete,
   `POST /drafts/regenerate`, `GET /passages`, keep compare-run.
4. Change status from one file revision to aggregate DB counts, stale-gold
   counts, and capability state. No filesystem paths.
5. Extend passage lookup to a caller-readable selected current document with
   keyset pagination and bounded locator search.
6. Regenerate drafts for one document using existing extraction,
   `source_family_id`, duplicate suppression, and `assign_splits`; insert only
   up to remaining capacity; never self-approve.
7. Keep compare-run as citation overlap, not Recall@10.
8. Keep route registration behind `APP_ENV in {local,test}` and the kill
   switch. Set local Compose default true.
9. Missing migration yields truthful 503, not an empty workspace.

## Acceptance checks

- Owner/admin CRUD, CAS, pagination, stale-gold, regeneration, and
  XSS-safe responses.
- Question/answer absent from list/status/error/log captures.
- Full detail only for owner/admin. Members 403. Inaccessible IDs 404.
- Disabled/staging/production routes absent/404.
- Old CLI store tests still pass.

## Negative tests

- Holdout rejected. Payload bounds enforced.
- Forged member cannot create or list cases.
- Stale row_version is 409.
- Compare-run before a completed owned run is rejected.

## Stop routes

- Stop rather than fall back to `.private-eval/` for HTTP.
- Do not add exam execution to “complete” the API.

## Required evidence

- Append contract-test commands/exits, OpenAPI update, Compose default
  change, 503-on-missing-migration proof, and P06-30 handoff.
