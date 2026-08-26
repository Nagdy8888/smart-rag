---
phase: 8
packet: 24
status: complete
title: "Canonical streaming overhaul amendment and policy ADR"
requirement_ids: [P08-24]
---

# Packet 24 — Canonical streaming overhaul amendment and policy ADR

Read the [Phase 8 shared contracts](../00-shared-contracts.md), the [Phase 8 visual contract](../00-visual-contract.md) when this packet owns frontend visuals, and the [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

Candidate ID `GOV-00` from the streaming/modularization suite. Do not
uncheck historical packets or renumber P08-22/P08-23.

## Preconditions

Documentation and plan-integrity only. P08-07 evidence already exists. No application source, migration, dependency, or runtime config edits.

## Allowed outputs

Additive P08-24 through P08-87 packet files, P06-16, ADR-verified-answer-paced-reveal, Phase 6/8 shared-contract amendments, visual/workspace-screen superseding notes, coverage/evidence/docs index updates, and an approved integrity-lock refresh after structural validation.

## Forbidden outputs

Application code, migrations, dependency pins, runtime secrets, hash-only lock refresh that conceals structural errors, renumbering P08-22/P08-23, or checking a packet without evidence.

## Ordered actions

Implement the following packet body. Do not summarize away file paths,
acceptance tests, or stop conditions.

1. Reconcile P08-07: existing evidence and packets 07-23 are present; check the wrapper item and set packet 07 status to complete.
2. Record ADR-verified-answer-paced-reveal distinguishing immediate verified-text ingestion, bounded presentation reveal, no pre-verification prose, skip/reduced-motion, and terminal independence.
3. Add P06-16 and link it from the Phase 6 wrapper and Phase 6 shared contracts.
4. Supersede Phase 8 shared-contract, visual-contract, P08-09, P08-15, and workspace-screens presentation rules that required updates-only streaming and no-delay verified insert.
5. Add additive packets P08-24 through P08-87 for the accepted streaming/modularization suite. Do not activate a sibling coding packet in this file.
6. Run verify_plan_integrity.py without --update, fix structure, then refresh the lock only after this approved amendment.

## Acceptance checks

P08-07 is checked. One amendment packet (this file) plus the authorized pending suite exist. The ADR supersedes the old presentation rule. Integrity verifier passes. No application code changed.

## Negative tests

Hash-only repair, renumbering P08-22/P08-23, or checking this packet without integrity output fails the packet.

- Fail closed on unauthorized, empty-success, duplicate-charge, and
  placeholder-control cases named in the packet body.
- Hostile/mixed-direction text remains escaped text nodes.

## Stop routes

Stop if structural validation fails. Do not edit application code. Do not uncheck historical packets 1-6 or 8-21.

## Required evidence

Append `P08-24` (`GOV-00`) proof to
[`docs/development/phase-08-frontend-integration-evidence.md`](../../../../../docs/development/phase-08-frontend-integration-evidence.md):
changed paths, exact commands/results, authorization/failure/idempotency/fallback
proof, architecture before/after line counts when files move, unverified
external checks, deviations/rollback, and handoff blockers.
