---
phase: 6
packet: 67
status: complete
title: "Add owner/admin document title rename and reindex one canonical copy."
requirement_ids: [P06-67]
---

# Packet 67 — Add owner/admin document title rename and reindex one canonical copy.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Load [`.cursor/skills/implement-api-security/SKILL.md`](../../../../../.cursor/skills/implement-api-security/SKILL.md)
and
[`.cursor/skills/implement-ingestion-pipeline/SKILL.md`](../../../../../.cursor/skills/implement-ingestion-pipeline/SKILL.md).

## Preconditions

- P06-66 live extra-terms RPC is proven.
- Live 2026-09-21 fact: five current copies share identical bytes and
  the same non-canonical title. Zero titles contain the book-name
  substring used by scoped Ask questions. No document-rename RPC
  exists. `app.update_conversation_title` and
  `app.delete_visible_document` exist.
- User approved an additive owner/admin `app.update_document_title`
  plus `PATCH /documents/{document_id}`. If that approval is later
  revoked, stop and ask; do not invent another product API.
- Production remains sample-blind. The canonical title string used on
  the hosted row is operational data, not a production code constant.

## Allowed outputs

- New additive migration `app.update_document_title(p_document_id
  uuid, p_title text)` `SECURITY INVOKER`, owner/admin only, modeled
  on `app.delete_visible_document`.
- FastAPI `PATCH /documents/{document_id}` with body `{ "title":
  string }`, same authorization as other document mutations.
- Tests: owner success, admin success, member 403, foreign/deleted
  indistinguishable not-found, empty/too-long title 422, OpenAPI
  update.
- One hosted operational rename of exactly one current copy, then
  exactly one `hybrid_index` requeue for that version.
- Live SQL proving exact-one current document matches the new title
  and the other four copies remain current with the old title.
- Evidence files named below.

## Forbidden outputs

- Deleting duplicate documents.
- Reindexing every copy.
- Uploading a sixth copy.
- Hardcoding the sample PDF hash, old title, new title, or document
  UUIDs in production code, prompts, tests, or migrations.
- Duplicate-aware `content_hash` resolution in this packet.
- Broad retrieval ranking changes.

## Ordered actions

1. Read `supabase/migrations/20260819105000_document_delete_rpc_v1.sql`
   and the documents router/service. Mirror owner/admin, not-found
   indistinguishability, and input validation.

2. Add a new timestamped migration. Do not edit applied migrations.
   Validate title non-empty after trim and a documented max length
   matching existing document-title constraints. Update `updated_at`.

3. Add `PATCH /documents/{document_id}` through existing document HTTP
   service patterns. Update OpenAPI. Do not invent a new auth stack.

4. Add tests listed in Acceptance checks. Tests use generic titles
   such as `Canonical Source Title` and must not quote the sample PDF.

5. Run unit, contract, and OpenAPI/migration checks.

6. Apply the migration to hosted `qsjivtwtmlmtksufqjik`. Prove
   `pg_proc` has `update_document_title`.

7. Using the live API or RPC as the document owner, rename exactly one
   current copy to a unique canonical title that the scoped Ask
   questions can resolve. Do not write that title into production
   files.

8. Requeue exactly one `hybrid_index` job for that document's current
   version. Wait until that job succeeds. Do not enqueue jobs for the
   other copies.

9. Prove live exact-one scope with count-only SQL: one current
   document has the new title; four current documents retain the old
   title; no extra current version was created.

## Acceptance checks

- Owner and admin can rename; members cannot.
- Foreign and deleted documents are indistinguishable not-found.
- Empty and over-long titles are rejected.
- OpenAPI includes the new PATCH.
- Hosted `pg_proc` shows `update_document_title`.
- Live counts prove exact-one current title match.
- Exactly one hybrid_index job was queued for the renamed version.
- No sample-PDF literals in production files.
- Duplicate copies remain current; none were deleted.

## Negative tests

- Member PATCH returns 403.
- Foreign UUID and deleted UUID return the same not-found.
- Empty title and whitespace-only title return 422.
- Reindex of a second copy or deletion of a duplicate fails the
  packet.
- Encoding the canonical title in Python/SQL tests fails.

## Stop routes

- Stop if the user did not approve the product rename API.
- Stop if exact-one live title match cannot be proven.
- Stop if hybrid_index for the renamed version fails.
- Stop if the migration would change `delete_visible_document`
  behavior.

## Required evidence

Create
[`p06-67-canonical-document-title-2026-09-21.md`](../../../../../docs/development/phase-06/p06-67-canonical-document-title-2026-09-21.md)
and append to
[`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md):

- Migration name and `pg_proc` proof.
- Test command/exits.
- Live counts: current copies, exact-one title match, jobs queued.
- Confirmation that production files contain no sample title/hash.
- Rollback: disable the PATCH/RPC in application code; keep the
  renamed live title; do not down-migrate; do not delete documents.

Commands:

```powershell
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier contract
uv run python scripts/ci/check_openapi.py
uv run python scripts/ci/check_migrations.py
git diff --check
```
