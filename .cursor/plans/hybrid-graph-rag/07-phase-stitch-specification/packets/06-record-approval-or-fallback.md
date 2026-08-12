---
phase: 7
packet: 6
status: pending
title: "Timebox user generation/review to five business days and two rounds; record approval or explicitly select the component-system fallback."
requirement_ids: [P07-06]
---

# Packet 6 — Timebox user generation/review to five business days and two rounds; record approval or explicitly select the component-system fallback.

Read the [Phase 7 shared contracts](../00-shared-contracts.md) and [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

- `P07-01` through `P07-05` are evidenced.
- `STITCH_BRIEF.md` and `API_UI_MAPPING.md` are complete, linked, and internally reviewed.
- Token/localization decisions, accessibility findings, contract gaps, and fallback candidates are explicit.

## Allowed outputs

- Dated user review records for at most two revision rounds within five business days.
- Explicit approval of usable accessible Stitch references or explicit component-system fallback selection.
- Final Phase 7 evidence and unambiguous Phase 8 handoff.

## Forbidden outputs

- A third revision round or open-ended wait disguised as phase progress.
- Approval based only on bundle presence, visual appeal, or inaccessible/unmapped frames.
- Silent fallback, production frontend implementation, checked packet boxes without proof, or phase completion without user acceptance.

## Ordered actions

1. Start and record the five-business-day review window, approver, artifacts, and acceptance criteria.
2. Present screen/state coverage, API mapping, token/localization decisions, RTL/mobile/accessibility findings, delivered-reference gaps, and unresolved contract blockers.
3. Run no more than two revision rounds and record requested changes and dispositions.
4. Obtain dated approval identifying accepted accessible references, or select and document the accessible component primitives and canonical tokens for fallback.
5. Produce the Phase 8 handoff with exact artifact versions/links, accepted frames, gap dispositions, fallback status, and blockers.

## Acceptance checks

- The review duration is at most five business days and revision count at most two.
- Approval proves implementable accessible references plus complete mapping/localization/token/gap decisions, or fallback selection is explicit and sufficient to implement.
- No unresolved contract gap is mislabeled as approved UI behavior.
- Phase 8 has one unambiguous implementation input and does not need to restart design generation.

## Negative tests

- Reject approvals lacking approver/date, accepted artifacts, accessibility/RTL review, mapping coverage, or gap disposition.
- Reject inaccessible exports, mock-dependent interactions, conflicting tokens, prohibited blur, or unauthorized diagnostics.
- Reject indefinite waiting; invoke the documented fallback when the bounded review ends without approval.

## Stop routes

- Stop Phase 8 handoff when a security/data/cost/acceptance contract gap remains blocking.
- At the bounded review deadline, choose the documented fallback instead of extending the design loop.

## Required evidence

Append `P07-06` proof to [`docs/development/phase-07-stitch-specification-evidence.md`](../../../../../docs/development/phase-07-stitch-specification-evidence.md): review dates/rounds, approver, artifact versions, accepted references or fallback, token/localization/accessibility decisions, gap dispositions, blockers, rollback notes, and the complete Phase 8 handoff.
