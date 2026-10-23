# Chat order and answer reading — 22 October 2026

## Confirmed ordering defect

Real authenticated transcript responses returned a user message followed by
its assistant message. The frontend blindly reversed that page, displaying
the answer before its question. The database function sorted an inner page
but did not guarantee order after the outer joins.

The frontend now deduplicates overlapping pages and sorts messages by actual
timestamps. Equal-time messages from the same run put the user first. The API
query now explicitly orders its returned page newest-first for its pagination
contract. Settled-turn overlays, historical citations and live SSE identities
are retained.

Authenticated HTTP and read-only cursor checks confirmed the repaired API order.
Repeated identical questions are matched by run identity so earlier turns do not
hide a new question or its answer.

## Shared response formatting

The changes apply through the shared answer renderer to saved and future
responses, not a particular test answer:

- Plain standalone source titles become headings when their shape is clear.
- PDF bullet symbols and both `1.` and `1)` ordered lists render as lists.
- Long Arabic and English explanations receive sentence-boundary reading
  breaks without dropping the ending.
- Ordinary prose paragraphs remain paragraphs instead of being automatically
  converted to a bullet list.
- Existing safe code, table, figure and source rendering remains in use. No
  raw HTML rendering or executable source content was introduced.
- Source-code syntax limitations receive explicit user-facing explanation.
- Mixed prose/code paragraphs retain both the introduction and the explanation
  after every complete fence. Code literals are decoded once, with Copy using
  the same text displayed to the user. Content remains React text nodes.

## Validation

The final focused frontend group passed 107 tests, including integration coverage
for both API message orders and regressions for Arabic reading breaks, source
headings, PDF bullets, and preserved paragraph boundaries. TypeScript, ESLint,
and the optimized Next.js production build passed after the final code-literal
correction. `git diff --check` also passed.

The local development frontend reads these source changes. This is not evidence
that Vercel was redeployed. Browser-control inventory was empty in this session,
so no current desktop/mobile visual inspection is claimed; component DOM
verification and the production build are the available evidence.
