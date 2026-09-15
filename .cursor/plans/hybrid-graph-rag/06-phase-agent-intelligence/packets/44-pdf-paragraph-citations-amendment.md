---
phase: 6
packet: 44
status: complete
title: "Authorize PDF paragraph-citation overlay, ADR, and packets P06-45 through P06-48."
requirement_ids: [P06-44]
---

# Packet 44 — Authorize PDF paragraph-citation overlay, ADR, and packets P06-45 through P06-48.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

This packet names no implementation skill. It edits Markdown and the
plan-integrity lock only.

## Preconditions

- Packets P06-01 through P06-16 and P06-19 through P06-41 are checked on
  `feature/advanced-web-research-mode`. P06-42 and P06-43 remain open.
  P06-17 live qualification remains blocked. P06-18 was not opened.
- User approved on 2026-09-15: company-PDF citations show canonical
  `app.documents.title`, the 1-based PDF viewer file page, and an
  ACL-checked exact supporting excerpt beside each factual paragraph.
- P06-37 through P06-43 already authorize advanced web research, so this
  overlay is numbered 44–48 to keep packet numbers contiguous.

## Allowed outputs

- Approved-deviation sections in
  [`00-global-contracts.md`](../../00-global-contracts.md) and
  [`06-phase-agent-intelligence.md`](../../06-phase-agent-intelligence.md).
- Cross-packet ownership note in
  [`00-shared-contracts.md`](../00-shared-contracts.md).
- [`docs/adr/ADR-pdf-paragraph-citations.md`](../../../../../docs/adr/ADR-pdf-paragraph-citations.md)
  plus index links from [`docs/README.md`](../../../../../docs/README.md) and
  [`docs/adr/README.md`](../../../../../docs/adr/README.md).
- Packet files P06-45 through P06-48 under this directory and wrapper links.
- Navigation note in
  [`hybrid-graph-rag_ab5281ef.plan.md`](../../../hybrid-graph-rag_ab5281ef.plan.md).
- Amendment log in [`99-source-coverage.md`](../../99-source-coverage.md).
- Plan-integrity lock update after structural checks pass.
- Evidence handoff in
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
  and
  [`p06-44-pdf-paragraph-citations-amendment-2026-09-15.md`](../../../../../docs/development/phase-06/p06-44-pdf-paragraph-citations-amendment-2026-09-15.md).

## Forbidden outputs

- Any Python, TypeScript, SQL, migration, prompt-file, Compose, or `.env`
  default change.
- Unchecking packets 1–43; renumbering P06-10 through P06-43 or
  P08-22/P08-23.
- Starting Packet 45 coding in the same markdown-only close unless the
  user requested the remaining sequence.
- Treating printed `page_label` as the chat page.
- Returning full chunks, signed Storage URLs, or source text over SSE.
- Retrofitting paragraph mappings onto historical null spans.
- Changing General, user-text, deterministic, or Web answer behavior.

## Ordered actions

1. Record that overlay packets are numbered 44–48 because P06-37–43 are
   taken and the integrity verifier requires contiguous order after 43.
2. Write the ADR: PDF viewer page, paragraph mappings, bounded excerpt,
   fail-closed verification, legacy honesty, rejected alternatives, and
   rollback.
3. Add approved-deviation bullets to global + Phase 6 wrapper: chat page
   is `page_index + 1`; excerpts require live ACL recheck; Web rows stay
   URL/title/hash only.
4. Create packet files P06-45 through P06-48 with required headings and
   unique `requirement_ids`.
5. Link packets 44–48 from the Phase 6 wrapper without changing packets
   1–43 titles or numbers. Record execution: after P06-41, run 44–48,
   then resume P06-42, P06-43, then P06-17.
6. Update docs index, ADR index, coverage log, and plan index navigation.
7. Run structural integrity checks, then refresh the lock.
8. Append P06-44 evidence. Do not mark complete until the user accepts the
   amendment, except when the user requested the remaining sequence in the
   same run.

## Acceptance checks

- Only Markdown and the plan-integrity lock changed in the Markdown close.
- Wrapper/packet titles match. Requirement IDs P06-44 through P06-48 are
  unique.
- Packets 1–43 titles and numbers unchanged.
- PDF viewer page versus printed `page_label` is explicit.
- Excerpt authorization boundary and 1000-character cap are explicit.
- Company insufficient evidence still never falls back to web or general
  knowledge.
- Markdown links, Mermaid in the new ADR, and plan-integrity tests pass.

## Negative tests

- Extra unlinked packet file, duplicate requirement ID, wrapper/packet
  title mismatch, or P08-22/P08-23 renumber fails the amendment.
- Unchecking historical packets, treating `page_label` as the chat page,
  or returning full chunks over API/SSE fails.
- Starting Packet 45 Python/SQL/TypeScript in this Markdown close fails
  unless the user requested the remaining sequence.

## Stop routes

- Stop if the verifier rejects the packet structure and the difference
  cannot be resolved without inventing a new loading contract.
- Stop if the amendment would require replacing web-research packet
  numbers 37–43.
- Do not edit application code to “make the docs true” in this packet.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
  and create
  [`p06-44-pdf-paragraph-citations-amendment-2026-09-15.md`](../../../../../docs/development/phase-06/p06-44-pdf-paragraph-citations-amendment-2026-09-15.md):
  files changed, plan-integrity command/exit, docs-tier command/exit,
  rollback (delete packets 44–48, ADR, deviation sections; restore prior
  lock), and P06-45 handoff.
