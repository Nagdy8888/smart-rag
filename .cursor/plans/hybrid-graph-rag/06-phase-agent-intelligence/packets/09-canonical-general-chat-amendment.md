---
phase: 6
packet: 9
status: pending
title: "Canonical amendment for general-chat strict-split, ADR, and packets P06-10 through P06-15."
requirement_ids: [P06-09]
---

# Packet 9 — Canonical amendment for general-chat strict-split, ADR, and packets P06-10 through P06-15.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

This packet names no implementation skill. It edits Markdown only.

## Preconditions

- Historical Phase 6 packets 1–8 have committed implementation evidence.
- The user approved the general-chat strict-split product contract on
  2026-08-25, including a separate live Studio graph and preservation of
  deterministic `query_studio`.

## Allowed outputs

- Approved-deviation sections in
  [`00-global-contracts.md`](../../00-global-contracts.md) and
  [`06-phase-agent-intelligence.md`](../../06-phase-agent-intelligence.md).
- [`docs/adr/ADR-general-chat-strict-split.md`](../../../../../docs/adr/ADR-general-chat-strict-split.md)
  plus index links from [`docs/README.md`](../../../../../docs/README.md) and
  [`docs/adr/README.md`](../../../../../docs/adr/README.md).
- Packet files P06-10 through P06-15 under this directory, wrapper links
  P06-09 through P06-15, and a Phase 8 wrapper note that P06-14 is a
  Phase 6/Phase 8 co-owned additive UI amendment.
- Plan-integrity lock update after structural checks pass.
- Evidence handoff in
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md).

## Forbidden outputs

- Any Python, TypeScript, SQL, JSON graph registration, environment default,
  migration, or prompt-file change.
- Unchecking historical completed Phase 6 packets 1–8.
- Unchecking historical completed Phase 8 packets or renumbering active
  P08-22/P08-23.
- Starting P06-10 coding in the same model run as this amendment unless the
  user explicitly requested the full remaining packet sequence after this
  packet's checks pass.

## Ordered actions

1. Add the approved-deviation section to the global contract and Phase 6
   wrapper. The text must record the strict split, no world-knowledge fallback
   for company questions, no blending, durable `answer` usage, real-JWT live
   Studio, and preservation of unbound `query_studio`.
2. Write the ADR with the accepted decisions and rejected alternatives from
   the approved product contract.
3. Create packet files P06-10 through P06-15. Copy the relevant instructions
   and acceptance checks. Each packet must name only the shared contracts and
   skills it actually requires.
4. Link packets 9–15 from the Phase 6 wrapper. Record P06-14 as a Phase 6/
   Phase 8 co-owned additive UI amendment on the Phase 8 wrapper without
   adding a new Phase 8 packet number.
5. Link the ADR from the documentation index and ADR index.
6. Update the plan-integrity lock only after
   `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py`
   structural checks pass.
7. Append P06-09 evidence. Do not mark this packet complete until the user
   accepts the amendment.

## Acceptance checks

- Only Markdown and the plan-integrity lock changed.
- Global/Phase 6 contracts, ADR, packet files, wrapper links, docs index, and
  reciprocal references agree.
- P06-10 is the next and only coding packet.
- Markdown links and plan-integrity tests pass.

## Negative tests

- A packet file missing required headings, a wrapper/packet title mismatch, a
  broken relative plan link, an extra unlinked packet file, a duplicate
  requirement ID, or a Phase 8 renumber of P08-22/P08-23 fails the amendment.

## Stop routes

- Stop if the repository's plan-integrity verifier rejects the new packet
  structure and the difference cannot be resolved without inventing a new
  loading contract.
- Do not edit application code to “make the docs true.”

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md):
  files changed, plan-integrity command/exit code, docs-link command/exit
  code, rollback (delete the new packets/ADR/deviation sections and restore
  the previous integrity lock), and P06-10 handoff.
