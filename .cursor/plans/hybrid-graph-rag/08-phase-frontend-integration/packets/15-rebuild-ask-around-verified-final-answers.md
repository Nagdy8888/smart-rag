---
phase: 8
packet: 15
status: pending
title: "Rebuild Ask around verified final answers"
requirement_ids: [P08-15]
---

# Packet 15 — Rebuild Ask around verified final answers

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-10 protocol and P08-14 shell exist. Move chat-app.tsx exactly once in this packet.

## Allowed outputs

Ask layout, sessions, composer, Generating/Verifying progress, verified final insertion, sources/details/feedback.

## Forbidden outputs

Fake streaming caret/typewriter. Inventing transcript history. Manual Hybrid/Combined send controls. Second file move later.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-15 — Rebuild Ask around verified final answers

Purpose: produce a focused RAG workspace using only real conversation/run/SSE contracts and the explicit verified-final-delivery decision.

Primary files:

- move current [`apps/frontend/src/components/chat-app.tsx`](apps/frontend/src/components/chat-app.tsx) once to `apps/frontend/src/components/chat/chat-app.tsx`
- components under [`apps/frontend/src/components/chat/`](apps/frontend/src/components/chat)
- update every import/test in this packet and delete the old source path
- chat styles, safe copy, action inventory, docs, and tests.

Implementation:

- Use a two-region desktop layout: optional compact Sessions rail/drawer plus the main answer workspace. Sources and diagnostics open in drawers; remove the duplicate permanent source column.
- Sessions use `GET /conversations`. New, Continue, and Delete are real actions. Continue validates with `GET /conversations/{id}`, selects it for future messages, clears only the local visible transcript, and states that prior transcript content is not exposed by the current API.
- On mobile, Sessions opens from a labeled sheet button; no gesture-only navigation.
- Prompt chips place text in the composer and never submit paid work.
- The sticky auto-resizing composer respects the server message limit and exposes one Send/Stop control.
- Show only real stages: connecting, queued, retrieving, generating, verifying, reconnecting, partial, complete, cancelled, and failed.
- During Generating/Verifying show progress, not a caret or fake typewriter. Insert the verified final SSE chunks immediately without artificial delay and announce the completed answer once.
- Render answer text as safe text with `dir="auto"`. Preserve already delivered verified text on later transport failure/cancel.
- Show citation chips only for real IDs; open one provenance drawer without fabricated preview/download text.
- Keep route/BM25/cache/coverage/tool diagnostics collapsed. Remove manual Hybrid/Combined/Table/Inspect send controls and unsupported nDCG/TTFB fields.
- Feedback appears only after a terminal answer, uses the exact server tag catalog, and reports real success/failure.
- Remove static “sources unavailable” and duplicate status/answer chrome.
- Use polite live regions for progress/reconnect/final-answer availability and assertive regions for blocking compatibility, budget, and error states.

Acceptance tests:

- A successful run shows Generating then Verifying, emits no answer text before verification, inserts a non-empty final answer before `completed`, and renders real citations.
- Continue, New, Delete, Send/Stop, Retry reconnect, Sources, Run details, prompt chips, and Feedback all have tested effects.
- No decorative/dead control, fake streaming caret, or invented transcript appears.
- Keyboard/screen-reader flows cover composer, sessions, sources, details, feedback, and reconnect.
- Mixed Arabic/English answer, code, URL, citation, and punctuation fixtures preserve readable bidi behavior.


## Copied visual specification

### Ask workspace component specification

#### Overall layout

- Use available height below topbar: `min-height: calc(100dvh - 56px)`.
- At `>=1280px`: 248px Sessions rail and `minmax(0, 1fr)` main workspace, 16px gap.
- At `<1280px`: Sessions rail becomes a left Sheet opened by a “Sessions” Secondary button.
- Main answer column max width is 880px and centered inside available space.
- There is no permanent right sources/diagnostics column.

#### `SessionRail`

- White bordered panel, 12px radius, vertical layout.
- Header: “Sessions” and compact Primary “New” button.
- Search is omitted because the API does not provide global search and local first-page search is misleading.
- Session row: 48px minimum, title one line, created timestamp, current indicator, overflow menu.
- Clicking row performs real Continue. Active row uses selected background.
- Overflow contains Delete only.
- Footer may contain Load more when cursor data supports it.
- Empty copy: “No sessions yet. Start a question to create one.”
- Continuing copy above transcript: “Continuing this session. Earlier messages are not available in this client.”

#### Chat empty state

- Icon: spark/search, not a robot avatar.
- Title: “Ask your company knowledge.”
- Body: “Answers use authorized documents and show available evidence.”
- Three prompt-fill chips maximum:
  - “Summarize an uploaded policy”
  - “Compare two documented values”
  - “Find a relationship between entities”
- Chips populate composer only; they never submit.

#### User message

- Align right, maximum width 78%.
- Accent-muted background, 12px radius with 4px bottom-right radius, 12px by 14px padding.
- Text 14px/22px, `dir="auto"`.
- No avatar, timestamp, edit, copy, or retry button unless backed by a contract.

#### Assistant answer

- Full-width transparent surface with a 3px evidence-colored left border and 16px left padding.
- Header row: spark icon, “Answer,” route StatusPill when real, and overflow with real actions only.
- Answer text 15px/24px for reading comfort.
- Do not show a streaming caret or typewriter animation. Show the real Generating/Verifying progress state, then insert verified final answer text without artificial delay.
- Partial/cancelled/error retains existing text and adds a StatusBanner below.
- Footer order: citations, feedback, then “Run details” disclosure.

#### `RunProgress`

- Compact horizontal/vertical step list using real status events.
- Known stage labels map to: “Preparing,” “Retrieving,” “Generating,” “Verifying.”
- Unknown stage renders safe neutral exact stage text in details, not as a new primary phase.
- Current stage uses info style; completed stages success; failure danger.
- Do not show percentages.

#### `ChatComposer`

- White bordered panel, 12px radius, shadow-1, 12px padding.
- Textarea borderless inside composer; focus ring surrounds composer container.
- Bottom toolbar: left character count/status; right Attach is absent unless a real chat attachment contract exists; primary Send/Stop at far right.
- Send button: 40px high, label and 16px arrow icon.
- Running state replaces Send with Secondary/quiet-danger “Stop” and square icon.
- `Enter` submits, `Shift+Enter` inserts newline; IME composition never submits.
- Disabled reason appears immediately above composer in a StatusBanner, not only tooltip.
- Draft remains after admission failure; clears only after successful admission.

#### `ReconnectState`

- Warning banner above composer.
- Copy: “Connection interrupted. Reconnecting… attempt X of Y.”
- Actions: “Cancel” and, after automatic ceiling, “Try again.”
- Keep partial answer visible.

#### `CitationChip`

- 28px high evidence-muted pill, evidence text, evidence border, 12px/16px weight 600.
- Label format: `[1] Source` when a safe source label exists; otherwise `[1] Evidence`.
- Opens real Sources drawer.
- No external-link icon unless a safe authorized URL exists in the actual contract.

#### `SourcesDrawer`

- Width 560px desktop, full width mobile.
- Header “Sources.”
- Group citations by safe source identity only when actual provenance supports it.
- Citation card shows index, document/chunk identifiers, page/sheet/range/URL locator fields actually present, and “Source unavailable” status when true.
- No fake excerpt, preview, download, relevance score, or open-source button.

#### `RunDetailsDrawer`

- Width 440px.
- Sections in order: Status, Route, Limitations, Cache/Coverage, Usage, Technical IDs.
- Closed by default.
- “Your usage” labels `/usage/me`; never “Company total.”
- IDs use monospace and Copy buttons with real clipboard feedback.
- No raw traces, prompts, provider secrets, source text, nDCG, or invented latency.

#### `FeedbackPopover`

- Opens from “Give feedback” Secondary button after terminal.
- First choose thumbs up/down, then required server tag Select, optional comment Textarea, Submit.
- Width 360px; actions right aligned.
- Success copy: “Feedback recorded.”
- Failure copy: “Feedback could not be recorded. Try again.”
- Popover remains open on failure.

## Acceptance checks

Successful run shows Generating then Verifying, then non-empty verified answer before completed. No decorative controls.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if SSE events required by the UI are not in the catalog. Do not invent events.

## Required evidence

Append `P08-15` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
