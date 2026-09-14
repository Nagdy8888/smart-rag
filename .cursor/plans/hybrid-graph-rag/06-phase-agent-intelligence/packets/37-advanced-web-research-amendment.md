---
phase: 6
packet: 37
status: pending
title: "Authorize advanced web research overlay, ADR, and packets P06-38 through P06-43."
requirement_ids: [P06-37]
---

# Packet 37 — Authorize advanced web research overlay, ADR, and packets P06-38 through P06-43.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

This packet names no implementation skill. It edits Markdown only.

## Preconditions

- Packets P06-01 through P06-16 and P06-19 through P06-36 are checked on
  `main`. P06-17 live qualification remains blocked. P06-18 was not opened.
- User approved on 2026-09-10: Ask dropdown Auto / Company documents /
  General / Web; Auto default; Auto resolves to exactly one effective
  mode; web retrieval uses Exa; development/free-tier only; staging and
  production fail closed.
- P06-27 through P06-36 already authorize hosted evaluation, so this
  overlay is numbered 37–43 to keep packet numbers contiguous.

## Allowed outputs

- Approved-deviation sections in
  [`00-global-contracts.md`](../../00-global-contracts.md) and
  [`06-phase-agent-intelligence.md`](../../06-phase-agent-intelligence.md).
- Cross-packet ownership note in
  [`00-shared-contracts.md`](../00-shared-contracts.md).
- [`docs/adr/ADR-advanced-web-research.md`](../../../../../docs/adr/ADR-advanced-web-research.md)
  plus index links from [`docs/README.md`](../../../../../docs/README.md) and
  [`docs/adr/README.md`](../../../../../docs/adr/README.md).
- Packet files P06-38 through P06-43 under this directory and wrapper links.
- Navigation note in
  [`hybrid-graph-rag_ab5281ef.plan.md`](../../hybrid-graph-rag_ab5281ef.plan.md).
- Amendment log in [`99-source-coverage.md`](../../99-source-coverage.md).
- Plan-integrity lock update after structural checks pass.
- Evidence handoff in
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
  and
  [`p06-37-advanced-web-research-amendment-2026-09-14.md`](../../../../../docs/development/phase-06/p06-37-advanced-web-research-amendment-2026-09-14.md).

## Forbidden outputs

- Any Python, TypeScript, SQL, migration, prompt-file, Compose, or `.env`
  default change.
- Unchecking packets 1–36; renumbering P06-10 through P06-36 or
  P08-22/P08-23.
- Starting Packet 38 coding in the same markdown-only close unless the
  user requested the remaining sequence.
- Enabling web research in staging or production.
- Treating Exa snippets as company RAG, BM25, LightRAG, or StructuredTable
  evidence.
- Falling back from insufficient company evidence to web or general
  knowledge.
- Blending company-document and web claims in one answer.
- Adding `web_search` to the optional-tool catalog.

## Ordered actions

1. Record that overlay packets are numbered 37–43 because P06-27–36 are
   taken and the integrity verifier requires contiguous order after 36.
2. Write the ADR: Exa provider, bounded search/fetch, URL-only citations,
   `WEB_SEARCH_ENABLED` plus `APP_ENV=local` gate, free-tier/rate limits,
   rollback, and rejected alternatives.
3. Add approved-deviation bullets to global + Phase 6 wrapper: dropdown
   contract; Auto resolves to exactly one of company / general / web;
   Web uses Exa; local only; production disabled; narrow Web-evidence
   exception.
4. Create packet files P06-38 through P06-43 with required headings and
   unique `requirement_ids`.
5. Link packets 37–43 from the Phase 6 wrapper without changing packets
   1–36 titles or numbers.
6. Update docs index, ADR index, coverage log, and plan index navigation.
7. Run structural integrity checks, then refresh the lock.
8. Append P06-37 evidence. Do not mark complete until the user accepts the
   amendment, except when the user requested the remaining sequence in the
   same run.

## Acceptance checks

- Only Markdown and the plan-integrity lock changed in the Markdown close.
- Wrapper/packet titles match. Requirement IDs P06-37 through P06-43 are
  unique.
- Packets 1–36 titles and numbers unchanged.
- Company insufficient evidence still never falls back to web or general
  knowledge.
- Web research explicitly forbidden when `APP_ENV` is not `local` or when
  the enable flag is false.
- Auto contract requires exactly one resolved effective mode.
- Markdown links, Mermaid in the new ADR, and plan-integrity tests pass.

## Negative tests

- Extra unlinked packet file, duplicate requirement ID, wrapper/packet
  title mismatch, or P08-22/P08-23 renumber fails the amendment.
- Unchecking historical packets, staging/production enablement language,
  or treating web results as canonical Supabase document evidence fails.
- Auto contract allowing simultaneous company retrieval and Exa search
  fails.

## Stop routes

- Stop if the verifier rejects the packet structure and the difference
  cannot be resolved without inventing a new loading contract.
- Stop if the amendment would require replacing hosted-eval packet numbers
  27–36.
- Do not edit application code to “make the docs true” in this packet.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
  and create
  [`p06-37-advanced-web-research-amendment-2026-09-14.md`](../../../../../docs/development/phase-06/p06-37-advanced-web-research-amendment-2026-09-14.md):
  files changed, plan-integrity command/exit, docs-tier command/exit,
  rollback (delete packets 37–43, ADR, deviation sections; restore prior
  lock), and P06-38 handoff.
