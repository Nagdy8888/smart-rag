---
title: "ADR: Quiet work-tool visual refresh supersedes Ink & Indigo theme values"
adr_id: ADR-quiet-tool-visual-refresh
status: accepted
owner: engineering-lead
last-reviewed: 2026-09-25
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-09-25"
audience: frontend, reviewers
supersedes: ADR-ink-indigo-visual-refresh
---

# ADR: Quiet work-tool visual refresh supersedes Ink & Indigo theme values

## Status

`accepted` on 2026-09-25. The user approved the quiet work-tool direction in Cursor chat on 2026-09-25.

## Context

The Ink & Indigo console matches the generated-design pattern of a SaaS card kit: an indigo-to-violet gradient on the logo, the auth panel, and empty states; a sparkle icon as the logo and the default empty-state icon; identical rounded cards with the same soft shadow, often nested; centered hero empty states; outlined suggestion chips; all-caps group labels; and developer notes in the UI.

The product is a tool for reading company documents. Citations are the core promise, so they are the only colored treatment. Everything else stays restrained.

## Decision

1. Replace the Ink & Indigo token block with the quiet work-tool values in `apps/frontend/src/app/globals.css` and `apps/frontend/src/lib/design-tokens.ts`: neutral canvas `#F7F7F5`, white surfaces, ink primary buttons, slate accent `#3B5B8C`, and evidence teal `#0A6F6E` for citations only.
2. Self-host IBM Plex Sans and IBM Plex Sans Arabic (weights 400, 500, 600). No runtime font download. No `Sparkles` icon.
3. Radius hierarchy: citation markers 4px, controls 6px, panels and cards 8px, overlays 10px, pills 999px. Resting surfaces have a border and no shadow (`--shadow-1: none`). Only overlays use `--shadow-2`.
4. No gradients anywhere.
5. Motion uses CSS only, on the transitions.dev duration scale (40ms to 500ms), with reduced-motion collapsing durations and delays. Historical messages never replay an entrance.
6. User-visible copy drops developer notes such as "UI state is not authorization." The BM25 degradation message stays.

## Superseded contract rules

The Phase 8 visual contract (`.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration/00-visual-contract.md`) still governs component inventory, required states, accessibility, security, responsive breakpoints, the answer reveal rules, and "Historical messages never replay the animation" (line 514). This redesign keeps that last rule by scoping Ask entrances to the live turn. The contract file is not edited. This ADR replaces these rules:

- Exact color theme (lines 31 to 65): the quiet work-tool values. Evidence teal is darker, and the accent is slate `#3B5B8C` instead of indigo `#4E5BD5`.
- Typography (lines 80 to 97): IBM Plex Sans replaces Inter, and the page title is 20/28 instead of 24/32.
- Radius (lines 139 to 141): controls 6px, cards 8px, overlays 10px, instead of 8px and 12px.
- Elevation (line 151): `--shadow-1` is `none`, so resting cards have no shadow.
- Primary button (line 190): an ink fill instead of the accent. Button weight is 500 instead of 600 (line 189).
- Auth layout (line 448): a 380px borderless form column instead of a 420px white card with a border and a shadow.
- Session rail (line 480): a flat rail with one hairline edge instead of a white bordered panel with a 12px radius.
- Chat empty state (lines 493 to 500): no icon. The prompt chips become a list of three rows that still only fill the composer and never submit.
- User message (line 505): a muted fill instead of accent-muted.
- Skeleton (line 334): `--color-surface-hover` instead of `#E9EDF2`.
- Motion (lines 157 to 162): hover transitions are 150ms instead of 120ms. Dialogs open in 250ms and side sheets in 400ms, instead of 160ms for both. Side sheets slide 24px, more than the 8px limit. Buttons and chips scale to 0.97 and 0.96 on press, where the contract says press feedback uses color change, not scale or bounce. Citation markers use a slight overshoot curve. These rules stay: no animated layout height, no gradients, and reduced motion makes everything immediate.
- Copy: the user-visible strings listed in the quiet work-tool implementation brief, step S9.

## Alternatives considered

Refining the dark rail only was considered, and so was an editorial serif direction. The user chose the quiet work tool on 2026-09-25.

## Consequences

Visual baselines are regenerated. Token and geometry tests are updated. IBM Plex ships under OFL-1.1, with its license in `apps/frontend/public/fonts/`.
