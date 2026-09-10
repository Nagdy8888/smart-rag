---
phase: 6
packet: 19
status: complete
title: "Authorize the local-only PDF evaluation workspace overlay, ADR, and packets P06-20 through P06-26."
requirement_ids: [P06-19]
---

# Packet 19 — Authorize the local-only PDF evaluation workspace overlay, ADR, and packets P06-20 through P06-26.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

This packet names no implementation skill. It edits Markdown only.

## Preconditions

- Packet 9 is accepted, including the 2026-08-26 strict-split remediation.
- The user approved a local-only combined review-and-test workspace on
  2026-09-10 and approved executing this overlay before Packet 10.
- Historical packets 1–8 stay checked. Packets 10–18 stay numbered and
  unchecked.

## Allowed outputs

- Approved-deviation sections already present in
  [`00-global-contracts.md`](../../00-global-contracts.md) and
  [`06-phase-agent-intelligence.md`](../../06-phase-agent-intelligence.md).
- [`docs/adr/ADR-local-pdf-evaluation-workspace.md`](../../../../../docs/adr/ADR-local-pdf-evaluation-workspace.md)
  plus index links.
- Packet files P06-20 through P06-26 under this directory and wrapper links.
- Plan-integrity lock update after structural checks pass.
- Evidence handoff in
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md).
- Reciprocal notes in
  [`hybrid-pdf-accuracy-remediation.md`](../../../../../docs/development/hybrid-pdf-accuracy-remediation.md)
  and [`99-source-coverage.md`](../../99-source-coverage.md).

## Forbidden outputs

- Any Python, TypeScript, SQL, JSON runtime profile, environment default,
  migration, or prompt-file change in this packet.
- Unchecking packets 1–8 or renumbering P06-10 through P06-18 or P08-22/P08-23.
- Starting Packet 10 coding.
- Opening holdout, freezing `hybrid_long_document_v1`, or claiming Recall@10
  from ungrounded labels.

## Ordered actions

1. Record that overlay packets are numbered 19–26 because the integrity
   verifier requires contiguous packet order.
2. Write the ADR with local-only storage, no privileged API DSN, human
   approval, holdout isolation, and rollback.
3. Create packet files P06-20 through P06-26 with required headings.
4. Link them from the Phase 6 wrapper without changing packets 10–18.
5. Update docs index, ADR index, overlay navigation, and coverage log.
6. Refresh the plan-integrity lock only after structural checks pass.
7. Append P06-19 evidence. Do not start P06-20 in a Markdown-only close
   unless the user requested the remaining overlay sequence.

## Acceptance checks

- Only Markdown and the plan-integrity lock changed in the Markdown close.
- Wrapper/packet titles match. Requirement IDs P06-19 through P06-26 are
  unique.
- Packet 10 files and titles are unchanged.
- Company insufficient evidence still never falls back to general knowledge.
- Holdout remains sealed and outside the workspace contract.

## Negative tests

- An extra unlinked packet file, duplicate requirement ID, wrapper/packet
  title mismatch, or P08-22/P08-23 renumber fails the amendment.
- Opening holdout or unchecking historical packets fails the amendment.

## Stop routes

- Stop if the verifier rejects the packet structure and the difference cannot
  be resolved without inventing a new loading contract.
- Do not edit application code to “make the docs true” in this packet.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md):
  files changed, plan-integrity command/exit, docs-link command/exit,
  rollback (delete overlay packets/ADR/deviation sections and restore the
  previous integrity lock), and P06-20 handoff.
