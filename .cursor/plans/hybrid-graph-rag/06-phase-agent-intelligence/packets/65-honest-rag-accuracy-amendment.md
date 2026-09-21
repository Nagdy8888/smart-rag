---
phase: 6
packet: 65
status: complete
title: "Authorize the detailed honest accuracy overlay, ADR, and packets P06-66 through P06-72."
requirement_ids: [P06-65]
---

# Packet 65 — Authorize the detailed honest accuracy overlay, ADR, and packets P06-66 through P06-72.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

This packet names no implementation skill. It edits Markdown and the
plan-integrity lock only.

## Preconditions

- Packets P06-01 through P06-16, P06-19 through P06-43, P06-49 through
  P06-61 are checked. P06-45 through P06-48 remain the PDF citation
  overlay and stay unchecked in this wrapper even when their code is
  on `main`. P06-62 through P06-64 stay unchecked until live evidence
  proves remaining items. P06-17 live qualification remains open.
  P06-18 was not opened.
- User approved on 2026-09-21: honest measurement, owner/admin document
  title rename, one canonical reindex, ID-only diagnostics, private
  gold repair, four-arm isolation, one proven-stage repair, GitHub
  green-check merge, then a frozen 30-question PDF sample.
- P06-58 through P06-64 already authorize general Hybrid retrieval
  accuracy, so this overlay is numbered 65–72 to keep packet numbers
  contiguous.

## Allowed outputs

- Approved-deviation sections in
  [`00-global-contracts.md`](../../00-global-contracts.md) and
  [`06-phase-agent-intelligence.md`](../../06-phase-agent-intelligence.md).
- Cross-packet ownership note in
  [`00-shared-contracts.md`](../00-shared-contracts.md).
- [`docs/adr/ADR-honest-rag-accuracy.md`](../../../../../docs/adr/ADR-honest-rag-accuracy.md)
  plus index links from [`docs/README.md`](../../../../../docs/README.md) and
  [`docs/adr/README.md`](../../../../../docs/adr/README.md).
- Packet files P06-66 through P06-72 under this directory and wrapper
  links.
- Navigation note in
  [`hybrid-graph-rag_ab5281ef.plan.md`](../../../hybrid-graph-rag_ab5281ef.plan.md).
- Amendment log in [`99-source-coverage.md`](../../99-source-coverage.md).
- Plan-integrity lock update after structural checks pass.
- Evidence handoff in
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
  and
  [`p06-65-honest-rag-accuracy-amendment-2026-09-21.md`](../../../../../docs/development/phase-06/p06-65-honest-rag-accuracy-amendment-2026-09-21.md).

## Forbidden outputs

- Any Python, TypeScript, SQL, migration, prompt-file, Compose, or
  `.env` default change.
- Unchecking packets 1–61; renumbering P06-10 through P06-64 or
  P08-22/P08-23.
- Reusing packet numbers 58–64 for this overlay.
- Checking P06-62, P06-63, or P06-64 from this markdown-only packet.
- Marking P06-17, P06-18, or Phase 6 complete.
- Starting Packet 66 coding in this markdown-only close unless the
  user requested the remaining sequence.
- Embedding the sample PDF hash, book title, question IDs, gold
  phrases, expected answers, page numbers, or benchmark aliases in
  production contracts.
- Raising `MODEL_INPUT_MAX_CHARS`, opening holdout, mutating frozen
  `hybrid_default_v1` bytes in place, pinning the failed
  `hybrid_long_document_v1.json` digest, authorizing a sixth upload, or
  authorizing company-to-Web fallback.

## Ordered actions

1. Record that overlay packets are numbered 65–72 because P06-58–64
   are taken and the integrity verifier requires contiguous order
   after 64.
2. Write the ADR: honest measurement, title rename, one canonical
   reindex, ID-only diagnostics, private gold, four-arm isolation, one
   proven repair, GitHub green-check merge, frozen 30-question sample,
   rejected alternatives, and rollback.
3. Add approved-deviation bullets to global + Phase 6 wrapper. Record
   execution: after P06-64, run 65–72, then leftover P06-17. Do not
   open P06-18.
4. Create packet files P06-66 through P06-72 with required headings
   and unique `requirement_ids`.
5. Link packets 65–72 from the Phase 6 wrapper without changing
   packets 1–64 titles or numbers.
6. Update docs index, ADR index, coverage log, and plan index
   navigation.
7. Run structural integrity checks, then refresh the lock with
   `--update`. `--update` is permitted only in this packet.
8. Append P06-65 evidence.

## Acceptance checks

- Only Markdown and the plan-integrity lock changed in the Markdown
  close.
- Wrapper/packet titles match. Requirement IDs P06-65 through P06-72
  are unique.
- Packets 1–64 titles and numbers unchanged.
- Numbering 65–72 versus the prior overlay’s 58–64 is explicit.
- Production contracts forbid sample-PDF hardcoding.
- Company insufficient evidence still never falls back to web or
  general knowledge.
- Markdown links, Mermaid in the new ADR, and plan-integrity tests
  pass.

## Negative tests

- Extra unlinked packet file, duplicate requirement ID, wrapper/packet
  title mismatch, or P08-22/P08-23 renumber fails the amendment.
- Unchecking historical packets, reusing 58–64, marking
  P06-17/P06-18 complete, or raising `MODEL_INPUT_MAX_CHARS` fails.
- Starting Packet 66 Python/SQL/TypeScript in this Markdown close
  fails unless the user requested the remaining sequence.

## Stop routes

- Stop if the verifier rejects the packet structure and the difference
  cannot be resolved without inventing a new loading contract.
- Stop if the amendment would require replacing retrieval-accuracy
  packet numbers 58–64.
- Do not edit application code to “make the docs true” in this packet.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md)
  and create
  [`p06-65-honest-rag-accuracy-amendment-2026-09-21.md`](../../../../../docs/development/phase-06/p06-65-honest-rag-accuracy-amendment-2026-09-21.md):
  files changed, plan-integrity command/exit, docs-tier command/exit,
  rollback (delete packets 65–72, ADR, deviation sections; restore
  prior lock), and P06-66 handoff.
- Commands:

  ```powershell
  uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update
  uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py
  uv run python scripts/check.py --tier docs
  git diff --check
  ```
