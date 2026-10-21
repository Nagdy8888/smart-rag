# Answer reading experience

Date: 21 October 2026.

## Observed in the signed-in app

Opened saved table and diagram answers, inspected their sources, and submitted a
fresh company-document question through the actual composer. The fresh run
completed with an answer, diagram, and three citations.

The Sources panel briefly announced zero citations while its request was still
loading. Its permanent footer also claimed previews were unavailable even though
the citation reader supports authorized PDF pages. The header's Sources action
did not target the latest saved run after opening a conversation. Run details
could show "No answer yet" next to a saved answer. Finally, persisted transcript
rendering dropped the live answer's inline citation chips after history refetched.

## Changes

- Show explicit source loading and recoverable failure states, including Retry.
  The header uses the saved run's citation count and opens that run's sources.
- Retain inline citations for the current run when its answer enters history.
  Citations from a different run are never attached to that answer. Selecting a
  live citation resets the source inspection target to its owning run.
- Hide empty live-run diagnostics when reading a saved conversation.
- Widen the answer area while keeping readable prose measures and opposite-side
  user/assistant alignment. Mixed prose/code/table/figure answers use natural
  blocks rather than numbering every media block as a list step.
- Separate an existing figure introduction, printed caption, and optional
  description without rewriting their words. Enlarge opens the already authorized
  image in a keyboard-accessible sheet; close restores focus. Loading and denied
  image requests have visible states, and object URLs are released on unmount.
- Add Copy answer with truthful success/failure feedback. Copy retains code
  whitespace and removes internal figure markers.
- Keep wide tables horizontally scrollable and keyboard focusable on mobile.
- Hide the permanent session rail on mobile and use the existing Sessions sheet.
  Selecting a session closes the sheet. Remove the duplicate mobile source
  control and retain its real citation count. Correct garbled loading labels.

## Verification scope

Added regression cases for loading/error recovery, clipboard success/denial,
current-versus-foreign run citations, caption text preservation, diagram
enlargement/cleanup, and denied image access. Existing authenticated browser
inspection and a fresh UI submission informed these changes; automated fixtures
remain labeled tests. No new backend endpoint, model call, answer rewrite, or
authorization bypass was added. This frontend pass is not a new live 25-question
evaluation or a claim that all original review findings are resolved.

Private response text, screenshots, and local logs remain outside Git. Production
publication and final check status must be verified against the resulting commit.

## Long text follow-up, October 21

Two questions were submitted through the signed-in app: one company-document
question and one general explanation requesting six sections. The latter
returned six headings and a substantial text answer. Inspection exposed sentence
splitting that made connected prose look like isolated steps, including an
automatically numbered conclusion.

The renderer now preserves authored paragraphs, headings, bullets, and numbered
lists. It does not invent numbered steps from sentence punctuation or paragraph
boundaries. Paragraph spacing, a bounded reading width, and mobile line spacing
provide hierarchy without modifying answer wording or citation indices.

Regression coverage includes multi-sentence paragraphs, headings with body text,
explicit lists, paragraph boundaries, and existing citation ownership/reveal
behavior. The local frontend suite passed 709 tests; type checking, production
build, and the action inventory passed. Lint retained five existing warnings.

The company-document response was incomplete in coverage and ended mid-word.
That is an answer-content issue observed during this UI check; this presentation
change does not claim to repair it or to constitute a new 25-question agent gate.
