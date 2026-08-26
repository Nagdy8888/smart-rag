---
phase: 8
packet: 58
status: pending
title: "Integrate paced verified-answer presentation without delaying protocol"
requirement_ids: [P08-58]
---

# Packet 58 — Integrate paced verified-answer presentation without delaying protocol

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `FEP-04` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-45, P08-56, and P08-57 complete.

## Allowed outputs

verified-answer-reveal.tsx and thin AnswerSurface/use-chat-run/ChatApp composition plus tests.

## Forbidden outputs

dangerouslySetInnerHTML. Holding citations/terminal/settlement/reconnect/feedback/send for reveal. Replaying animation on historical messages.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Live assistant renders visibleText; chat.answerText stays authoritative. Show full answer and selection/copy intent complete pacing. Announce Verified answer ready once. Company-route fixture: no prose through verify start, then prefix, then full text with terminal already available.

## Acceptance checks

Component tests prove waiting/revealing/complete, skip, reduced motion, and protocol independence.

## Negative tests

A historical message replaying animation fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if ChatApp would re-own reveal scheduling.

## Required evidence

Append `P08-58` (`FEP-04`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
