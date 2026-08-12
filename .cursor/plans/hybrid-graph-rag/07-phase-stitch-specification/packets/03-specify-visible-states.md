---
phase: 7
packet: 3
status: pending
title: "Specify every loading, empty, error, permission, quarantine, quota, compatibility, limitation, fallback, partial-readiness, budget, and degraded state."
requirement_ids: [P07-03]
---

# Packet 3 — Specify every loading, empty, error, permission, quarantine, quota, compatibility, limitation, fallback, partial-readiness, budget, and degraded state.

Read the [Phase 7 shared contracts](../00-shared-contracts.md) and [canonical frontend contract](../../shared/frontend/stitch-nextjs-contract.md).

## Preconditions

- `P07-01` and `P07-02` have verified contracts, screen prompts, tokens, and direction decisions.
- Required server states and sanitized error contracts are known.

## Allowed outputs

- Complete state matrices, messages, transitions, and screen examples in the two Phase 7 frontend documents.
- Explicit limitation, authorization, fallback, and unresolved-gap records.

## Forbidden outputs

- Fabricated terminal success, optimistic authority, hidden paid-work admission, or graph prose as evidence.
- Unauthorized count/title/source leakage or raw provider/internal errors.
- Generic state labels that omit required recovery, ownership, or fallback behavior.

## Ordered actions

1. Build a per-surface matrix for first load, loading, empty, success, partial, refusal, error, permission, MFA, quarantine, quota, compatibility, cancellation, reconnect, fallback, budget, and degraded service.
2. Cover auth recovery/revocation; upload/URL approval/attestation/scan/quarantine/parse/OCR/media/readiness/backlog/deletion; chat diagnostics; tables; graph inspection/blindness; tools/admin; usage/rates/audit; and settings.
3. Specify BM25 projection/unavailability, LightRAG fallback, deadline/partial, route correction, figure/media limitation, historical relationship, full-summary refusal, negation clarification/refusal, and contradictory-authority presentation.
4. Define API minimum-client blocking before paid work, startup failure, version switchover, and unknown additive SSE-event handling.
5. Add recovery actions, role visibility, focus/live-region treatment, and safe generic production copy for every applicable state.

## Acceptance checks

- Every state family in the packet title is represented for each applicable canonical surface.
- `Graph Pending` and authorized ACL-restricted graph blindness are distinct and reveal no unauthorized metadata.
- Dense+term BM25 degradation, Hybrid fallback, limitation, refusal, and partial-answer states are truthful and non-alarming.
- Quota, budget, rate, quarantine, compatibility, and retry actions map to real server decisions.

## Negative tests

- Exercise unauthorized, expired, oversize, stale-scan, incompatible-client, disconnect, duplicate-submit, deadline, BM25-down, LightRAG-down, and insufficient-evidence examples.
- Reject copy that implies graph-only answering, hidden retry spending, complete summaries without coverage, or exhaustive negation without proof.
- Reject states that expose internal exception text or restricted source identity.

## Stop routes

- Stop when a required state has no verified server signal, authorization rule, or safe recovery path.
- Record the unresolved owning-phase gap rather than designing a fictional transition.

## Required evidence

Append `P07-03` proof to [`docs/development/phase-07-stitch-specification-evidence.md`](../../../../../docs/development/phase-07-stitch-specification-evidence.md): state-matrix coverage, reviewed copy/examples, negative scenarios, authorization-leak review, contract gaps, and verification results.
