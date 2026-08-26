---
phase: 8
packet: 57
status: pending
title: "Reveal verified answers with a Unicode-safe presentation engine"
requirement_ids: [P08-57]
---

# Packet 57 — Reveal verified answers with a Unicode-safe presentation engine

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `FEP-03` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

P08-55 complete. ADR-verified-answer-paced-reveal is in force.

## Allowed outputs

verified-answer-segment.ts, use-verified-answer-reveal.ts, and fake-clock tests.

## Forbidden outputs

UTF-16 slicing, setInterval, persisted presentation cursor, or coupling to SSE chunk size.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

Segment with Intl.Segmenter grapheme or return [text]. Animate only current-session runs. 2.5s ceiling, <=90 publications, intermediate prefix for >80 graphemes, prefix-preserving growth, skip/reduced-motion/historical immediate, cancel rAF on key change/unmount.

## Acceptance checks

Joined segments equal input for Arabic, emoji ZWJ, bidi, citations. Long answer has >=2 paints, completes by 2500ms, <=90 publications.

## Negative tests

A broken grapheme or restarting on growth fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if Intl.Segmenter is missing; reveal the full string rather than a custom slicer.

## Required evidence

Append `P08-57` (`FEP-03`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
