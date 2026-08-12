---
phase: 7
status: active
title: Phase 7 shared contracts
---

# Phase 7 shared contracts

Use this file with the [Phase 7 wrapper](../07-phase-stitch-specification.md), exactly one packet in this directory, and the single [Stitch/Next.js contract](../shared/frontend/stitch-nextjs-contract.md).

## Specification ownership

Phase 7 owns reviewed [`STITCH_BRIEF.md`](../../../../docs/frontend/STITCH_BRIEF.md), [`API_UI_MAPPING.md`](../../../../docs/frontend/API_UI_MAPPING.md), canonical localization and design-token decisions, delivered-reference acceptance or fallback, and unresolved contract-gap disposition. It specifies Phase 8 behavior but does not implement the production frontend.

Phase 6's real thin UI and typed Auth/API/SSE contracts are inputs. Inventory repository reality before writing UI claims. Missing fields, endpoints, events, states, and authorization behavior remain explicit gaps; no mock, placeholder, invented schema, or fake success may close them.

## Shared specification requirements

- Cover every screen, visible diagnostic, state family, API mapping, Arabic/bidirectional fixture, responsive frame, accessibility behavior, and security boundary in the [canonical contract](../shared/frontend/stitch-nextjs-contract.md).
- Keep `Auto` as normal chat default and reserve manual modes for the advanced testing surface.
- Treat server authorization, current-version/ACL checks, durable budgets, idempotency, sequence/reconnect behavior, and canonical evidence as authoritative.
- Specify limitation and degradation messaging without leaking unauthorized counts, titles, source text, diagnostics, or internal errors.
- Reconcile machine-readable token definitions, prose guidance, and delivered frame values. Record one approved palette, radius, elevation, typography, spacing, and no-blur decision.
- Timebox user-run generation/review to five business days and two revision rounds. Approval must identify usable accessible references; otherwise document the selected component primitives and design-token fallback.

## Ordered packet discipline

Complete packets `P07-01` through `P07-06` in order. One model run selects exactly one unchecked packet, quotes its exact title, states its acceptance checks, and records evidence before any checkbox can be checked. Packet completion never marks the phase complete.

## Verification and stop routes

Inspect actual repository contracts and pinned primary dependency documentation. Run repository-defined checks applicable to changed specification artifacts and validate links, mappings, fixtures, and review records.

Stop and report when a prerequisite/sign-off is incomplete; a real contract contradicts planned security, data, cost, or acceptance semantics; a required dependency cannot be verified; real authorization/idempotency/deadline/budget/provenance/fallback behavior cannot be exercised; only a fake or skipped proof is available; or a launch-blocking review fails after bounded repair.

## Evidence contract

All packet proof is appended to [`docs/development/phase-07-stitch-specification-evidence.md`](../../../../docs/development/phase-07-stitch-specification-evidence.md). Include packet ID, changed artifacts, verified source contracts, commands/results, positive and negative review evidence, unresolved external assumptions, deviations/ADR approval, rollback notes, and Phase 8 handoff blockers. Do not set phase status complete until the wrapper's final done gate is proven and accepted.
