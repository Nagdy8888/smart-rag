# User-flow review and Web citations — 2026-10-26

## Delivered locally

Web citation chips now open the same supporting-passage reader used by company documents. The reader identifies the website, preserves its title, shows the saved supporting excerpt, and provides a separate safe original-page link that opens a new tab without a referrer. Unavailable and unsafe sources receive no external link; company storage locators remain private. Web citations never request the PDF-page endpoint. Citation navigation and historical source inspection retain their existing server-authorized APIs.

Closing a reader opened from the source list now returns keyboard focus to the persistent Sources button, rather than an unmounted list chip. Desktop and 390px mobile journeys exercise this behavior.

The live checkpoint m19 failure has a narrow regression fix: numbers alone cannot restore a verifier-rejected claim as an unrelated source excerpt. Existing quoted-text and identifier correction behavior remains covered by the verifier regression tests. This does not fix every potential citation-binding failure. The separate m12 generation problem remains open pending live regression evidence.

Answer-generation timeouts now display an operational timeout message rather than stating that the company evidence could not support an answer. No route deadlines, accounting rules, model-call ceilings, authorization, or provider budgets were relaxed. Existing typed terminal behavior is unchanged.

## User-flow checks

An authenticated isolated browser on the running local app opened the existing diagnostic conversation, company source reader, Admin overview and document library through normal UI controls. The Web reader journey uses explicitly controlled citation/history responses, live sign-in, keyboard activation, desktop/mobile layouts, saved excerpts, and focus return. Its screenshots prove the reader UI, not successful live Web search.

The user's Edge extension timed out on connection. Isolated browser tests were used for verification; no claim is made that the personal Edge tab was changed during this review. The database stayed running. The local API was restarted after confirming zero active query runs, then returned healthy readiness.

## Live question blocker

A normal authenticated attempt at m22 in the existing conversation returned HTTP 402. It was not admitted and did not start a model run. Company and caller monthly limits remain $100. No new temporary increase was applied.

`tests/fixtures/web-citations-smoke15-v1.json` contains 15 prepared development questions, including English and Arabic. Reference material was checked on RFC Editor, W3C, the official Python tutorial and PostgreSQL documentation. These questions are not a holdout, and have not been executed against the app's Web provider. The 29 remaining company questions likewise remain incomplete. A separate budget decision is pending; neither preparation nor mocked citation tests count as a live evaluation pass.

## Validation

- Complete backend unit suite passed (existing skips retained).
- Verifier, timeout-copy, native-reproduction and code-continuation regressions: 51 passed.
- Frontend suite: 787 passed.
- Authenticated browser journeys: 2 passed; Web-reader fixture desktop/mobile plus live read-only company/history/admin/library journey.
- Ruff lint/format and strict Pyright passed for the backend changes.
- Final frontend typecheck, lint (zero errors, three existing image-optimization warnings) and production build passed after the focus/title changes.

No hosted deployment, new source ingestion, checkpoint deletion, holdout change, or permanent budget change was performed.
