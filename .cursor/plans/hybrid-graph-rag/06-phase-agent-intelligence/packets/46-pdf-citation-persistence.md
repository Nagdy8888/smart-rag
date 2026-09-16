---
phase: 6
packet: 46
status: pending
title: "Persist ACL-safe PDF citation traces, page repair, and conversation history."
requirement_ids: [P06-46]
---

# Packet 46 — Persist ACL-safe PDF citation traces, page repair, and conversation history.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md),
[`implement-supabase-security`](../../../../../.cursor/skills/implement-supabase-security/SKILL.md).

Do not load frontend skills.

## Preconditions

- P06-45 paragraph/span/link contracts exist.
- Requirement IDs: `CIT-PAGE-001`, `CIT-TITLE-002`, `CIT-SPAN-004`,
  `CIT-LEAF-005`, `CIT-ACL-008`, `CIT-HISTORY-009`, `CIT-LEGACY-010`,
  `CIT-COMPAT-011`, `CIT-BOUNDS-012`.
- Latest applied migrations stay untouched. Add the next expand-only
  file after the newest existing migration.

## Allowed outputs

- New migration under `supabase/migrations/`, provisionally
  `20260915140000_pdf_paragraph_citations_v1.sql`
- `packages/core/src/smart_rag_core/query_answer/citations.py`
- `packages/core/src/smart_rag_core/query_admission/repository/records.py`
- `packages/core/src/smart_rag_core/ingestion/canonical/repository.py`
- `scripts/ops/repair_pdf_page_numbers.py`
- FastAPI citation/transcript schemas, services, and routers
- Unit/contract tests listed below
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- Changing v1/v2/v3 RPC signatures.
- Frontend rendering.
- Sending excerpts or page text through SSE.
- Operator/service-role DSNs on the API path.
- Destructive reset against `*.supabase.co`.

## Ordered actions

1. Add nullable `app.citations.paragraph_index` with a check allowing
   `NULL` or `0..5`. Keep `snippet` as the bounded exact excerpt.
2. Preflight `(run_id, citation_index)` duplicates. Stop if real
   duplicates exist. Otherwise add a unique index.
3. Add `app.insert_run_citation_v2`: lock owned run; ACL/current-version
   recheck; resolve exactly one representative leaf containing the span;
   require one distinct PDF `page_index`; store leaf ID, span, paragraph
   index, and locator diagnostics without raw text; serialize by run and
   index; exact replay returns the existing ID; different replay raises
   `query_citation:replay_conflict`; cap 12 rows.
4. Add `app.list_run_citations_v4` returning typed `paragraph_index`,
   `document_title`, `pdf_page_number`, and `evidence_excerpt`. Recompute
   PDF page from locator `page_index + 1`. Return excerpt only when it
   still occurs in live canonical `raw_text`. Strip title/page/excerpt on
   ACL/current-version/deletion/locator/span failure. Preserve Web rows
   as URL/title/hash only.
5. Passage persistence calls v2. Table citations keep their existing
   path. Bound company persistence failure must not stream an apparently
   verified uncited answer. Unbound Studio/test graphs may skip honestly.
6. Refresh `page_number = EXCLUDED.page_number` on canonical chunk
   upsert. Add dry-run/batched `repair_pdf_page_numbers.py` using locator
   `page_index + 1`, reporting IDs and counts only.
7. Add `app.list_conversation_messages_v2` with nullable `run_id` and
   bounded `app.list_conversation_citations_v1` for at most 50
   server-supplied owned run IDs.
8. Extend HTTP `CitationResponse` and `ConversationMessage` additively.
   Escape title/heading/excerpt. Batch-load history citations.

## Acceptance checks

- Leaf citation on viewer page 25 displays/stores page 25.
- Parent resolves to one child on page 25; two matching children fail.
- Null/empty/non-contained span fails.
- Multi-page locators fail.
- Stored `page_number=12` with locator `page_index=24` returns 25.
- Printed `page_label=12` never changes `pdf_page_number`.
- Idempotent replay, conflicting replay, citation 13, foreign run/conversation
  404/not-found, ACL/delete/current-version strip, hostile excerpt escape,
  history batching, and legacy null paragraph/span honesty all pass.

## Negative tests

- v4 using `page_label` for the displayed page fails the packet.
- Returning excerpt without live ACL/current-version checks fails the
  packet.
- Hiding a database integrity failure as an empty list fails the packet.

## Stop routes

- Stop if `(run_id, citation_index)` duplicates block uniqueness.
- Stop if a representative leaf spans multiple page indices and cannot
  be repaired without guessing.
- Stop if contract tests only pass by skipping the database boundary.

## Required evidence

- Migration check, unit/contract pytest, ruff, pyright, and whether a
  labelled non-hosted `SUPABASE_DB_URL` was used. Handoff: typed HTTP
  fields for P06-47.
