---
title: "ADR: Quiet console restyle supersedes Field and slate theme values"
adr_id: ADR-quiet-console-restyle
status: accepted
owner: engineering-lead
last-reviewed: 2026-10-08
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-10-08"
audience: frontend, reviewers
supersedes: ADR-quiet-tool-visual-refresh
---

# ADR: Quiet console restyle supersedes Field and slate theme values

## Status

`accepted` on 2026-10-08. The user approved a whole-console restyle in Cursor chat on 2026-10-08.

## Context

The live console had drifted to The Field: a dark teal frame (`#0e1c24`), a cream work plate (`#f4f1ea`), a lime accent (`#d8f821`), 24px radii, and negative letter-spacing. The accepted quiet-work-tool ADR still specified a warm canvas and a slate accent (`#3B5B8C`). Both treatments read as a single banned family for an operational tool: cream, or dark slate chrome.

Routes, auth, and answer behavior stay. The change is the visual system.

## Decision

1. Replace the token block in `apps/frontend/src/app/globals.css` and `apps/frontend/src/lib/design-tokens.ts` with a light canvas `#F6F7F8`, white surfaces, ink primary buttons `#1A1D21`, green accent `#0F6E56`, and evidence `#155E75` for citations only.
2. `--color-field`, `--color-field-fg`, and `--color-plate` remain as aliases of the canvas, ink text, and white surface.
3. The shell is a light top bar with a 1px bottom border. Main content is full-bleed: the plate has no radius, no fill, and no inset of its own.
4. Radius: controls 6px, cards and overlays 8px, pills 999px. Letter-spacing is 0. `html` uses `color-scheme: light`. No gradients and no blur.
5. IBM Plex Sans and IBM Plex Sans Arabic stay self-hosted. Lucide remains the icon set. Empty, error, and diagnostic copy stay.

## Alternatives considered

Restoring the 2026-09-25 slate accent was rejected because that hue is the dark-blue family this restyle leaves behind. Keeping The Field and only shrinking the radius would leave the cream plate and dark frame.

## Consequences

Token and geometry tests match the new hex and the top-bar shell. [DESIGN_SYSTEM.md](../frontend/DESIGN_SYSTEM.md) and [design-tokens-and-primitives.md](../frontend/design-tokens-and-primitives.md) follow this ADR. [ADR-quiet-tool-visual-refresh.md](./ADR-quiet-tool-visual-refresh.md) is superseded for color, radius, and chrome.
