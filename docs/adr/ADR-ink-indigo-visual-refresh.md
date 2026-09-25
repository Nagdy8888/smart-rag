---
title: ADR — Ink & Indigo visual refresh supersedes Precision Workspace theme values
adr_id: ADR-ink-indigo-visual-refresh
status: superseded
superseded_by: ADR-quiet-tool-visual-refresh
owner: engineering-lead
last-reviewed: 2026-08-25
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-08-25"
audience: frontend, reviewers
---

# ADR: Ink & Indigo visual refresh supersedes Precision Workspace theme values

## Status

`superseded` by [ADR-quiet-tool-visual-refresh](./ADR-quiet-tool-visual-refresh.md) on 2026-09-25. The user approved a bolder visual redesign after
auditing the live console: keep Next.js 16 + React 19, keep the existing
Auth/API/SSE contracts, and replace the light all-white Precision Workspace
hex values with an ink navigation rail and deeper indigo accent.

## Context

The functional overhaul (P08-13) locked a light gray canvas, indigo
`#4E5BD5`, Inter, and 8/12px radii. The live product still read as a generic
admin console. The user rejected a framework rewrite and asked for an
impressive, non-generic look.

## Decision (accepted)

1. Supersede the P08-13 "Exact color theme" hex values, type scale, radii,
   shadows, and motion tokens with the Ink & Indigo token block in
   [`apps/frontend/src/app/globals.css`](../../apps/frontend/src/app/globals.css)
   and [`apps/frontend/src/lib/design-tokens.ts`](../../apps/frontend/src/lib/design-tokens.ts).
2. Scope is tokens, typography (self-hosted Inter Display for headings), and
   composition. Security, accessibility, and API contracts are unchanged.
3. `--gradient-brand` may appear only on the auth brand panel, the empty-state
   icon tile, and the nav brand logo tile. No gradient on controls. No
   `backdrop-filter`. No new npm UI libraries.
4. Evidence teal remains reserved for citations. WCAG AA contrast and
   `prefers-reduced-motion` remain mandatory.

## Consequences

- Existing Phase 8 visual snapshots and token assertions must be updated in
  the same change.
- Shell, Ask, auth, and surface packets consume these tokens; they do not
  invent a second palette.
