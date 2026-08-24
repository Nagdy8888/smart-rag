---
phase: 8
packet: 18
status: pending
title: "Rebuild bounded Graph inspection"
requirement_ids: [P08-18]
---

# Packet 18 — Rebuild bounded Graph inspection

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-14 shell exists. Move graph-explorer.tsx once. Tables packet is separate.

## Allowed outputs

Search-select-inspect, list-first plus optional React Flow, depth/key/result clamps, inspector, duplicate SVG removal.

## Forbidden outputs

Relationship editing. Third custom SVG. Unauthorized counts/titles. Tables rebuild.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-18 — Rebuild bounded Graph inspection

Purpose: retain graph evidence inspection while removing the duplicate custom SVG and unsupported relationship editing.

Primary files:

- move current `apps/frontend/src/components/graph-explorer.tsx` once under `apps/frontend/src/components/graph/`
- existing graph components/helpers, tests, docs, and inventory; update imports and delete the old path in this packet.

Implementation:

- Use search → select entities/document → inspect.
- Default to list-first results and one optional React Flow canvas. Remove the third custom SVG implementation.
- Clamp depth to 1–3, entity keys to 12, and results to 200 with visible truthful bounds.
- Provide one persistent inspector for identity, hop/support, canonical locator, and limitation codes.
- Distinguish Graph Pending, graph outage/fallback, and ACL blindness without unauthorized counts/titles.
- Fit, zoom, list/canvas toggle, and selection must be labeled and functional. Relationship editing is absent, not disabled.

Acceptance tests:

- Entity search, document-seeded inspect, bounds, list/canvas toggle, locator inspection, pending/outage/ACL behavior, and empty state pass.
- Large/mixed-direction labels, keyboard controls, focus return, and mobile overflow pass.
- No duplicate canvas or relationship-edit control ships.


## Copied visual specification

### Graph page component specification

#### Layout

- PageHeader title “Graph.”
- Description: “Inspect bounded entities and relationships backed by authorized evidence.”
- At `>=1280px`: 300px search panel, flexible result panel, 320px inspector.
- At 1024–1279px: search plus result; inspector is right Drawer.
- Below 1024px: stacked search, list/canvas result, inspector Drawer.

#### Entity search panel

- SearchInput label “Search entities.”
- Submit/search executes only for trimmed queries meeting current API minimum.
- Results are 48px rows with object type StatusPill, safe ID/name, support metadata.
- Clicking a result selects it and adds a selected entity chip.
- Maximum 12 selected. At limit, show helper “You can inspect up to 12 entities.”
- Selected chips have real Remove controls.
- Depth Select has exact options 1, 2, 3.
- Primary action “Inspect graph.”

#### Result toolbar

- Left: result count and limitation pill.
- Right: Tabs “List” and “Canvas,” then Fit control only in Canvas.
- No Edit, Add relationship, Expand unlimited, Depth 5, Export, or Save buttons.

#### Graph list

- Default accessible representation.
- Each row: object type, object ID, hop, support, and Select.
- Selection opens inspector.
- Empty: “No authorized graph evidence matched this inspection.”

#### React Flow canvas

- White surface with subtle 16px grid dots using border color.
- Nodes: 168px wide, white, 8px radius, 1px border; selected node accent border and accent-muted background.
- Node first line object type caption, second safe object ID, footer hop/support.
- Edges: 1.5px border-strong; selected path evidence color.
- Controls bottom-right: zoom in, zoom out, fit, each labeled IconButton.
- Mini-map is omitted unless it remains legible and accessible at the bounded 200-node limit.
- Node click selects; canvas itself is not an editor.

#### Graph inspector

- Title “Evidence details.”
- Definition list: Type, Object ID, Document ID, Version ID, Chunk ID, Hop, Support.
- Locator cards show page, section path, sheet/range, or safe URL fields that actually exist.
- Limitation banners appear below details.
- No vendor prose or relationship editing.

## Acceptance checks

Entity search, document-seeded inspect, bounds, list/canvas toggle, pending/outage/ACL honesty, no duplicate canvas.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a graph mutation API does not exist; omit editing rather than showing a disabled editor.

## Required evidence

Append `P08-18` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
