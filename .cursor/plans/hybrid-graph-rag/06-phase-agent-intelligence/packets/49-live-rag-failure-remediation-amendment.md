---
phase: 6
packet: 49
status: complete
title: "Authorize live RAG failure remediation overlay, ADR, and packets P06-50 through P06-57."
requirement_ids: [P06-49]
---

# Packet 49 — Authorize live RAG failure remediation overlay, ADR, and packets P06-50 through P06-57.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

This packet names no implementation skill. It edits Markdown and the
plan-integrity lock only.

## Preconditions

- Packets P06-01 through P06-16, P06-19 through P06-43, and P06-44 are
  checked. P06-45 through P06-48 remain the PDF citation overlay and
  stay unchecked in this wrapper even when their code is on `main`.
  P06-17 live qualification remains open. P06-18 was not opened.
- User approved on 2026-09-16: bound evidence fitting, grounded claim
  release, graceful terminals, additive transcript metadata, reload
  citations, Postgres reconnect, host-worker plus Exa lifecycle, then
  leftover P06-17 without holdout.
- P06-44 through P06-48 already authorize PDF paragraph citations, so
  this overlay is numbered 49–57 to keep packet numbers contiguous.

## Allowed outputs

- Approved-deviation sections in
  [`00-global-contracts.md`](../../00-global-contracts.md) and
  [`06-phase-agent-intelligence.md`](../../06-phase-agent-intelligence.md).
- Cross-packet ownership note in
  [`00-shared-contracts.md`](../00-shared-contracts.md).
- [`docs/adr/ADR-live-rag-failure-remediation.md`](../../../../../docs/adr/ADR-live-rag-failure-remediation.md)
  plus index links from [`docs/README.md`](../../../../../docs/README.md) and
  [`docs/adr/README.md`](../../../../../docs/adr/README.md).
- Packet files P06-50 through P06-57 under this directory and wrapper
  links.
- Navigation note in
  [`hybrid-graph-rag_ab5281ef.plan.md`](../../../hybrid-graph-rag_ab5281ef.plan.md).
- Amendment log in [`99-source-coverage.md`](../../99-source-coverage.md).
- Plan-integrity lock update after structural checks pass.
- Evidence handoff in
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
  and
  [`p06-49-live-rag-failure-remediation-amendment-2026-09-16.md`](../../../../../docs/development/phase-06/p06-49-live-rag-failure-remediation-amendment-2026-09-16.md).

## Forbidden outputs

- Any Python, TypeScript, SQL, migration, prompt-file, Compose, or
  `.env` default change.
- Unchecking packets 1–48; renumbering P06-10 through P06-48 or
  P08-22/P08-23.
- Reusing packet numbers 44–52 for this overlay.
- Marking P06-17, P06-18, or Phase 6 complete.
- Starting Packet 50 coding in this markdown-only close unless the
  user requested the remaining sequence.
- Raising `MODEL_INPUT_MAX_CHARS`, opening holdout, mounting a raw
  Docker socket, or authorizing company-to-Web fallback.

## Ordered actions

1. Record that overlay packets are numbered 49–57 because P06-44–48
   are taken and the integrity verifier requires contiguous order
   after 48.
2. Write the ADR: fitting, exact-duplicate suppression, reserves,
   grounded release, graceful terminals, transcript v3, reconnect,
   host-worker/Exa, rejected alternatives, and rollback.
3. Add approved-deviation bullets to global + Phase 6 wrapper. Record
   that `answer_v3`/`verifier_v2` are the new pins because `answer_v2`
   is the PDF citation prompt, and that transcript SQL is
   `list_conversation_messages_v3` because v2 already returns
   `run_id`.
4. Create packet files P06-50 through P06-57 with required headings
   and unique `requirement_ids`.
5. Link packets 49–57 from the Phase 6 wrapper without changing
   packets 1–48 titles or numbers. Record execution: after P06-48,
   run 49–57, then leftover P06-17. Do not open P06-18.
6. Update docs index, ADR index, coverage log, and plan index
   navigation.
7. Run structural integrity checks, then refresh the lock with
   `--update`. `--update` is permitted only in this packet.
8. Append P06-49 evidence. Do not mark complete until the user accepts
   the amendment, except when the user requested the remaining
   sequence in the same run.

## Acceptance checks

- Only Markdown and the plan-integrity lock changed in the Markdown
  close.
- Wrapper/packet titles match. Requirement IDs P06-49 through P06-57
  are unique.
- Packets 1–48 titles and numbers unchanged.
- Numbering 49–57 versus the umbrella plan’s 44–52 is explicit.
- Prompt pin is `answer_v3`/`verifier_v2`; transcript RPC is v3.
- Company insufficient evidence still never falls back to web or
  general knowledge.
- Markdown links, Mermaid in the new ADR, and plan-integrity tests
  pass.

## Negative tests

- Extra unlinked packet file, duplicate requirement ID, wrapper/packet
  title mismatch, or P08-22/P08-23 renumber fails the amendment.
- Unchecking historical packets, reusing 44–48, marking P06-17/P06-18
  complete, or raising `MODEL_INPUT_MAX_CHARS` fails.
- Starting Packet 50 Python/SQL/TypeScript in this Markdown close
  fails unless the user requested the remaining sequence.

## Stop routes

- Stop if the verifier rejects the packet structure and the difference
  cannot be resolved without inventing a new loading contract.
- Stop if the amendment would require replacing PDF-citation packet
  numbers 44–48.
- Do not edit application code to “make the docs true” in this packet.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
  and create
  [`p06-49-live-rag-failure-remediation-amendment-2026-09-16.md`](../../../../../docs/development/phase-06/p06-49-live-rag-failure-remediation-amendment-2026-09-16.md):
  files changed, plan-integrity command/exit, docs-tier command/exit,
  rollback (delete packets 49–57, ADR, deviation sections; restore
  prior lock), and P06-50 handoff.
- Commands:

  ```powershell
  uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update
  uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
  uv run python scripts/check.py --tier docs
  git diff --check
  ```
