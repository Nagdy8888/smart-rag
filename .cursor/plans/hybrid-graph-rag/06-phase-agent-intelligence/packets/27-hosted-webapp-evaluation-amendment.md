---
phase: 6
packet: 27
status: complete
title: "Authorize the hosted-evaluation workspace amendment, ADR, and packets P06-28 through P06-36."
requirement_ids: [P06-27]
---

# Packet 27 — Authorize the hosted-evaluation workspace amendment, ADR, and packets P06-28 through P06-36.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

This packet names no implementation skill. It edits Markdown and the
plan-integrity lock only.

## Preconditions

- Packet 9 is accepted. Overlay packets P06-19 through P06-26 are checked.
- Historical packets 1–8 stay checked. Packets 10–18 stay numbered.
- The user approved hosted quiz labels, production-corpus Recall@10,
  holdout exclusion, freeze exclusion, and feedback coexistence on 2026-09-10.

## Allowed outputs

- [`docs/adr/ADR-hosted-webapp-evaluation-workspace.md`](../../../../../docs/adr/ADR-hosted-webapp-evaluation-workspace.md)
  plus superseded status on the local-file ADR.
- Approved-deviation sections in
  [`00-global-contracts.md`](../../00-global-contracts.md) and
  [`06-phase-agent-intelligence.md`](../../06-phase-agent-intelligence.md).
- Packet files P06-27 through P06-36 under this directory and wrapper links.
- Docs index, ADR index, coverage log, governance residual-risk note,
  configuration intent, and evaluation/admin pointers.
- Plan-integrity lock update after structural checks pass.
- Evidence handoff in
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md).

## Forbidden outputs

- Any Python, TypeScript, SQL, JSON runtime profile, environment default,
  migration, Compose default, prompt-file, or hosted mutation.
- Marking managed Supabase region/DPA/backup rows `verified`.
- Starting Packet 10 coding or P06-28 in this run.
- Unchecking packets 1–8 or 19–26, or renumbering P06-10 through P06-18
  or P08-22/P08-23.
- Opening holdout, freezing `hybrid_long_document_v1`, or claiming a live
  Recall@10 number from this markdown packet.

## Ordered actions

1. Record that hosted-evaluation packets are numbered 27–36 because the
   integrity verifier requires contiguous packet order after P06-26.
2. Write the hosted-workspace ADR with the 2026-09-10 user decisions,
   residual-risk exception, and rollback.
3. Mark the local-file ADR superseded for custody and official Recall@10
   while preserving its historical overlay record.
4. Create packet files P06-28 through P06-36 with required headings.
5. Link them from the Phase 6 wrapper without changing Packet 10's file
   or title. Record execution order: this packet, then P06-10 acceptance,
   then P06-28 through P06-36, then P06-11.
6. Update docs indexes, governance matrices (exception only), configuration
   intent, and coverage log.
7. Refresh the plan-integrity lock only after structural checks pass.
8. Append P06-27 evidence. Stop for user acceptance before any code packet.

## Acceptance checks

- Only Markdown and the plan-integrity lock changed in this close.
- Wrapper/packet titles match. Requirement IDs P06-27 through P06-36 are
  unique.
- Packet 10 files and titles are unchanged.
- The old no-table decision is superseded. Hosted 365-day custody and
  production-corpus metric are explicit.
- Feedback coexistence, holdout exclusion, qualification one-shot, rollback,
  and P06-10 dependency are canonical.
- Managed region/DPA/backup remain unverified; residual-risk exception is
  recorded rather than silently verified.
- Integrity verifier and docs links pass.

## Negative tests

- An extra unlinked packet file, duplicate requirement ID, wrapper/packet
  title mismatch, or P08-22/P08-23 renumber fails the amendment.
- Starting P06-10 or P06-28 in this Markdown close fails the amendment.
- Opening holdout or unchecking historical packets fails the amendment.

## Stop routes

- Stop if the verifier rejects the packet structure and the difference cannot
  be resolved without inventing a new loading contract.
- Stop rather than mark hosted governance verified without provider evidence.
- Do not edit application code to “make the docs true” in this packet.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md):
  files changed, plan-integrity command/exit, docs-link command/exit,
  residual-risk exception, rollback (delete packets 27–36 and the new ADR,
  restore the local-file ADR status and previous integrity lock), and P06-10
  handoff. Request explicit user acceptance before Packet 10 coding.
