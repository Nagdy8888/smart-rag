---
phase: 6
packet: 42
status: pending
title: "Implement four-option Ask dropdown, Web origin, progress, citations, and resume."
requirement_ids: [P06-42]
---

# Packet 42 — Implement four-option Ask dropdown, Web origin, progress, citations, and resume.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md).

Do not load ingestion or retrieval skills.

## Preconditions

- P06-40 wire values and P06-41 progress/citation contracts exist.
- Inspect `chat-stage.tsx`, `use-chat-scope.ts`, `chat.ts`, citation chip
  href helper, banners, transcript CSS, and existing tests that assume
  Company files as default.

## Allowed outputs

- Dropdown labels exactly Auto, Company documents, General, Web in that
  order. Default Auto.
- Hide or disable Web when meta says `WEB_SEARCH_ENABLED` is false
- `answer_origin="web"` banner and citations for Web answers
- `shouldShowCitations` true for company, web, and legacy null
- Clickable chips only when `source_kind=web` and `isSafeHttpUrl`;
  `rel="noreferrer"`. Company Storage URLs stay non-href
- Progress copy: Searching… / Reading… / Verifying…
- Tests: `chat-app.test.tsx`, `use-chat-scope.test.tsx`,
  `save-to-quiz` if affected, Playwright core-rag surfaces, API contract
- `docs/frontend/CORE_RAG_SURFACES.md`, action inventory, workspace
  screens, packet evidence

## Forbidden outputs

- Default remaining Company files / company_documents
- Labels “Company files” or “General knowledge”
- Clickable company citation hrefs
- Rendering excerpts, snippets, or HTML bodies
- Frontend Exa key or client-side fetch of result URLs
- Changing paced-reveal or hold-until-verify

## Ordered actions

1. Add `web` to `REQUESTED_SEARCH_SCOPES` and default Auto.
2. Relabel the trigger and options. Keep persisted conversation scope
   on resume.
3. Map `web_search` / `web_read` / `verify_answer` progress.
4. Enable `citationChipHref` only for `source_kind=web` after
   `isSafeHttpUrl`.
5. Update tests that still expect Company files default.
6. Document the four labels and Auto-exactly-one behavior.

## Acceptance checks

- New chat dropdown default is Auto.
- Forced Web send includes `"requested_search_scope":"web"`.
- Disabled Web cannot be selected, or selection fails closed from API.
- Web answers show origin and URL chips; company answers stay
  non-clickable.
- Resume restores Auto/company/general/web without mixing evidence.
- Playwright/core tests pass without live Exa.

## Negative tests

- Unsafe or non-http URL is not an href.
- Company citation never becomes `href`.
- Web option hidden when flag is false.

## Stop routes

- Stop if tests still assume Company files as the default.
- Stop if citation href would apply to company documents.

## Required evidence

- Screenshot or test names for default Auto, four labels, Web chips,
  disabled Web, and resume; handoff to P06-43.
