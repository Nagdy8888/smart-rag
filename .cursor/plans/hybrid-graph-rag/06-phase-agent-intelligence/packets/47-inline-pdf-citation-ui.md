---
phase: 6
packet: 47
status: pending
title: "Render book title, PDF viewer page, and exact excerpt beside each answer paragraph."
requirement_ids: [P06-47]
---

# Packet 47 — Render book title, PDF viewer page, and exact excerpt beside each answer paragraph.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills: [`implement-rag-frontend`](../../../../../.cursor/skills/implement-rag-frontend/SKILL.md).

Do not load Python answer-generation or SQL-migration skills.

## Preconditions

- P06-46 typed HTTP fields exist: `paragraph_index`, `document_title`,
  `pdf_page_number`, `evidence_excerpt`, message `run_id`, and message
  `citations`.
- Requirement IDs: `CIT-PAGE-001`, `CIT-TITLE-002`, `CIT-PARA-003`,
  `CIT-HISTORY-009`, `CIT-LEGACY-010`.

## Allowed outputs

- `apps/frontend/src/lib/types/chat.ts`
- `apps/frontend/src/lib/api/chat-run.ts`
- `apps/frontend/src/lib/api/chat.ts`
- `apps/frontend/src/lib/citation-label.ts`
- `apps/frontend/src/components/chat/answer-surface.tsx`
- `apps/frontend/src/components/chat/citation-drawer.tsx`
- `apps/frontend/src/components/chat/hooks/use-chat-queries.ts`
- `apps/frontend/src/components/chat/chat-app.tsx`
- `apps/frontend/src/components/chat/chat-transcript.module.css`
- Frontend unit/E2E tests listed below
- Packet evidence under `docs/development/phase-06/`

## Forbidden outputs

- `dangerouslySetInnerHTML` for answer or excerpt text.
- Falling back to `page_label` for company PDF chips.
- Attaching `paragraph_index=null` rows to a paragraph.
- Putting source text into SSE diagnostic rendering.
- Changing General, user-text, deterministic, or Web origin gating.

## Ordered actions

1. Parse the four typed citation fields and message `run_id/citations`.
   Keep stripping arbitrary snippet/passage/html/content/body/text/excerpt/span
   keys from provenance. Accept only top-level `evidence_excerpt`.
2. Treat invalid or negative `pdf_page_number` and out-of-range
   `paragraph_index` as `null`.
3. Format available company PDF chips as
   `<document_title> · PDF page <pdf_page_number>`. Missing title uses
   `Source · PDF page N`. Missing page uses
   `<title> · PDF page unavailable`. Unavailable sources show only
   `Source unavailable`.
4. Split verified company answer text on `\n\n`. Render each paragraph
   through `UserText` with that paragraph's chips immediately after it.
5. Keep legacy unmapped citations in a footer labeled
   `Legacy run sources (not mapped to a paragraph)`.
6. During paced reveal, do not show a citation before its verified
   paragraph is fully visible.
7. Use the same renderer for live `GET /runs/{id}/citations` and
   historical `ConversationMessage.citations`.
8. Drawer heading is `<title> — PDF page N`. Show Book/source, PDF page,
   optional section, and `Supporting passage` via `UserText` with
   `dir="auto"`. No download/Storage URL.

## Acceptance checks

- Two paragraphs each show only their own citation.
- One paragraph can show two source chips.
- Viewer page 25 plus printed label 12 displays only `PDF page 25`.
- Drawer title, page, and excerpt match.
- Refresh and older-history pagination preserve mappings.
- Legacy rows stay in the labeled footer.
- Hostile title/excerpt render as text. Arabic/RTL uses `dir="auto"`.
- Keyboard opens/closes the drawer and restores focus.

## Negative tests

- Using `citationDisplayPage()` / `page_label` for a company PDF chip
  fails the packet.
- XSS via excerpt/title or raw HTML insertion fails the packet.
- Showing citations before paced-reveal paragraph visibility fails the
  packet.

## Stop routes

- Stop if the UI would require raw HTML or privileged Storage URLs.
- Stop if history citations cannot be rendered without N+1 fetches from
  the browser.
- Do not start P06-48 evaluation scoring in this packet.

## Required evidence

- Vitest, ESLint, `tsc --noEmit`, and frontend build exits. Handoff:
  UI mapping and drawer contract for P06-48.
