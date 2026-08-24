---
phase: 8
packet: 17
status: complete
title: "Rebuild deterministic Tables"
requirement_ids: [P08-17]
---

# Packet 17 — Rebuild deterministic Tables

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

P08-14 shell exists. Move tables-app.tsx once. Do not edit Graph in this packet.

## Allowed outputs

Guided TableQueryPlan, one Analyze action, provenance, Export removal, failure preservation.

## Forbidden outputs

Raw SQL. Standalone export. Graph canvas work. Unknown columns.

## Ordered actions

Implement the following packet body from the approved overhaul plan. Do not summarize away file paths, acceptance tests, or stop conditions.

## Packet P08-17 — Rebuild deterministic Tables

Purpose: retain bounded structured-table analysis while removing unsupported controls and isolating this surface from Graph work.

Primary files:

- move current `apps/frontend/src/components/tables-app.tsx` once to `apps/frontend/src/components/tables/tables-app.tsx`
- table helpers/components, API types, tests, docs, and inventory; update imports and delete the old path in this packet.

Implementation:

- Read `tableId`/document context from the URL and preselect only a real accessible manifest.
- Keep a guided `TableQueryPlan` with allow-listed columns, predicates, aggregations, grouping, order, and comparison; never accept raw SQL.
- Provide one Analyze primary action and preserve the exact submitted plan beside results.
- Render deterministic rows first, then provenance/source ranges. Label client sorting as display-only.
- Remove Export because there is no standalone export contract.
- Preserve the plan on empty manifest, 422, 403/404, 429, or server failure.

Acceptance tests:

- URL preselection, valid analyze, invalid plan, sorting, provenance drawer, failure preservation, and absence of Export pass.
- Unknown columns/operators/raw SQL are rejected before submission.
- Keyboard operation, mixed-direction cells, and mobile table overflow pass.


## Copied visual specification

### Tables page component specification

#### Layout

- PageHeader title “Tables.”
- Description: “Run bounded calculations on structured data with exact cell provenance.”
- At `>=1024px`: 320px manifest sidebar and main results area; below that manifest picker is a Select.

#### Manifest sidebar

- White bordered panel, 12px radius.
- Header “Available tables.”
- Rows show safe table/sheet identity and document ID metadata.
- Active row uses selected treatment.
- Empty: “No structured tables are available.”

#### Plan builder

- White Card, title “Analysis plan.”
- Field order: Table, Columns, Filters, Aggregation, Group by, Sort, Comparison.
- Optional sections start collapsed and open via real “Add filter,” “Add aggregation,” etc.
- Repeating row has inputs plus labeled Remove IconButton.
- One Primary “Analyze” button at bottom right.
- No raw SQL editor, natural-language fake planner, Export, Save, or Share button.

#### Results

- Header row: “Results,” row count, and Secondary “View provenance” when ranges exist.
- DataTable numeric cells right aligned and use tabular numerals.
- Generated narrative is shown only if returned by an existing typed contract and clearly separated; otherwise omit.
- Empty successful result: “The analysis returned no rows.”

#### Provenance drawer

- Header “Cell provenance.”
- List exact document/version/table/sheet/range fields from response.
- Monospace for cell ranges.
- No fake source link.

## Acceptance checks

URL preselection, valid/invalid analyze, sorting, provenance, no Export, mixed-direction overflow pass.

## Negative tests

- Fail closed on unauthorized, empty-success, duplicate-charge, and placeholder-control cases named in the packet body.
- Prove removal rather than permanent-disabled UI for unsupported actions.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if a displayed column is not in the allow-list. Do not add export because a button used to exist.

## Required evidence

Append `P08-17` proof to [`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md): changed paths, exact commands/results, authorization/failure/idempotency/fallback proof, unverified external checks, deviations/rollback, and handoff blockers.
