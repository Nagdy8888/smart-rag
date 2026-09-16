---
phase: 6
packet: 53
status: complete
title: "Add additive transcript-v2 run metadata and ACL-safe bounded citation-detail contracts."
requirement_ids: [P06-53]
---

# Packet 53 — Add additive transcript-v2 run metadata and ACL-safe bounded citation-detail contracts.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md),
[`implement-supabase-security`](../../../../../.cursor/skills/implement-supabase-security/SKILL.md).

## Preconditions

- P06-52 is recorded. Branch is `fix/rag-reliability-and-citations`.
- `app.list_conversation_messages_v2` already returns `run_id` only.
  This packet adds `app.list_conversation_messages_v3` with
  `citation_count` and `source_kind`. Keep v1 and v2 callable.
- Inspect applied migrations, transcript service, citation RPCs, and
  OpenAPI before editing. Do not modify applied SQL files.

## Allowed outputs

- New expand-only migration
  `supabase/migrations/20260916100000_conversation_transcript_run_links_v3.sql`
- `apps/backend/src/smart_rag_api/services/conversation_transcript.py`
- `apps/backend/src/smart_rag_api/routers/conversations.py`
- `apps/backend/src/smart_rag_api/routers/query_runs.py`
- `apps/backend/src/smart_rag_api/schemas/fastapi_security.py`
- `apps/backend/src/smart_rag_api/services/query_runs.py`
- Generated DB types and `docs/api/openapi.foundation.json`
- Contract tests listed below, API docs, and packet evidence

## Forbidden outputs

- Editing
  `supabase/migrations/20260825200000_conversation_transcript_v1.sql`
  or
  `supabase/migrations/20260915140000_pdf_paragraph_citations_v1.sql`.
- Changing a function return type in place.
- Putting excerpts in transcript listings, SSE, logs, or traces.
- Reducing the accepted PDF excerpt cap below 1000 characters.
- Adding durable `answer_origin` storage.
- Applying the migration to staging/production.
- Frontend Sources-restore work (Packet 54).

## Ordered actions

1. Create `app.list_conversation_messages_v3` with v1 arguments and
   ordering plus nullable `run_id`, `citation_count` clamped `0..50`,
   and nullable `source_kind` (`company_document`, `web`, or null).
2. Return `run_id` only when `runs.id=messages.run_id`,
   `runs.conversation_id=messages.conversation_id`, and
   `runs.creator_user_id=caller_user_id`.
3. Fail the contract rather than choosing one `source_kind` when a
   run owns both company and Web citations.
4. Keep v1 and v2 grants/signatures untouched and callable.
5. Add `GET /runs/{run_id}/citations/{citation_id}` returning
   `CitationDetailResponse`. Company excerpt requires live
   ACL/current/non-deleted recheck and restricted-read audit. Cap
   remains 1–1000 characters. Web detail uses persisted run-scoped
   excerpt and validated HTTPS URL only.
6. Unauthorized, deleted, mismatched, or unavailable sources return
   IDOR-safe not-found/unavailable behavior and no excerpt.
7. Apply the additive migration only to development project
   `qsjivtwtmlmtksufqjik` after listing remote migrations. Never paste
   the DSN.

## Acceptance checks

- Matching run IDs and citation counts on owned transcripts.
- v1 and v2 remain callable.
- Foreign/deleted conversation yields no run ID.
- Mismatched run/conversation cannot leak.
- Citation detail is bounded and contained in canonical text.
- Foreign/deleted/ACL-revoked sources return no excerpt.
- Web URL must be safe HTTPS.
- OpenAPI remains additive.

## Negative tests

- Replacing v2 in place fails the packet.
- Returning excerpts from the transcript list fails.
- Choosing a `source_kind` when both company and Web citations exist
  fails.

## Stop routes

- Stop if project id is not `qsjivtwtmlmtksufqjik`.
- Stop if applying SQL would require a down-migration.
- Do not start Packet 54 UI work until this contract is proven.

## Required evidence

- Migration lint, OpenAPI, contract tests, ruff, pyright. Record that
  v1 and v2 coexist without pasting SQL bodies.
- Commands:

  ```powershell
  uv run python scripts/ci/check_migrations.py
  uv run python scripts/ci/check_openapi.py
  uv run python -m pytest tests/contract/test_conversation_transcript.py tests/contract/test_citation_acl_recheck.py tests/contract/test_web_citation_persist.py tests/unit/test_answer_citations_persist.py -q
  uv run ruff check apps/backend/src/smart_rag_api packages/core/src/smart_rag_core/query_admission tests/contract/test_conversation_transcript.py tests/contract/test_citation_acl_recheck.py
  uv run pyright apps/backend/src/smart_rag_api packages/core/src/smart_rag_core/query_admission
  git diff --check
  ```

- Commit `feat(api): expose run-linked transcript citations`.
