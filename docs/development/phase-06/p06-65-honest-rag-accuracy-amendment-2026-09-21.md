---
title: P06-65 honest RAG accuracy amendment
owner: engineering-lead
status: complete
last-reviewed: 2026-09-21
audience: engineering, reviewers, security
---

# P06-65 — Honest RAG accuracy overlay (2026-09-21)

Parent index:
[phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Markdown-only authorization. No application code, prompt, migration,
environment default, Compose default, or `.env` value changed in this
packet.

Requirement IDs: `P06-65` through `P06-72`.

## Plan requirement

Quote: authorize the detailed honest accuracy overlay, ADR, and packets
P06-66 through P06-72.

Positive checks: ADR with Mermaid, alternatives, security, rollback,
and contiguous numbering after retrieval-accuracy packets 58–64; unique
requirement IDs P06-65–P06-72; packets 1–64 unchanged; production
contracts forbid sample-PDF hardcoding; company insufficient evidence
never falls back to web or general knowledge; missing live fields are
`unknown` and block promotion.

Negative checks: no Python/TypeScript/SQL/runtime JSON/env default; no
reuse of packet numbers 58–64; no P06-17/P06-18/Phase 6 complete; no
holdout; no checking P06-62/P06-63/P06-64 from this markdown packet.

## Files changed

- [ADR-honest-rag-accuracy.md](../../adr/ADR-honest-rag-accuracy.md)
- [`.cursor/plans/hybrid-graph-rag/00-global-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/00-global-contracts.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md)
- packet files `65`–`72` under
  [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/)
- [`.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md`](../../../.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md)
- [`.cursor/plans/hybrid-graph-rag/99-source-coverage.md`](../../../.cursor/plans/hybrid-graph-rag/99-source-coverage.md)
- [`.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json`](../../../.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json)
- [docs/README.md](../../README.md), [docs/adr/README.md](../../adr/README.md)

## Numbering and branch base

P06-58 through P06-64 already authorize general Hybrid retrieval
accuracy. Integrity requires contiguous packet numbers, so this overlay
is P06-65 through P06-72 on `fix/honest-rag-accuracy` from current
`main`.

## Verification

| Command | Exit |
| --- | --- |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update` | 0 (`Split plan integrity updated: 228 canonical files`) |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | 0 (`Split plan integrity verified: 228 canonical files`) |
| `uv run python scripts/check.py --tier docs` | 0 (markdownlint 0 issues / 295 files; links and Mermaid render; frontend action inventory verified) |
| `git diff --check` | 0 |

## Proven

- Packets 1–64 remain numbered. P06-45 through P06-48 stay unchecked.
  P06-62 through P06-64 stay unchecked. P06-17 and P06-18 stay
  unchecked. Phase 6 stays incomplete.
- Honest measurement, live extra-terms RPC deploy, owner/admin
  document title rename, one canonical reindex, ID-only diagnostics,
  human-sealed private gold, four-arm isolation, one proven-stage
  repair, live qualification, GitHub green-check merge, and a frozen
  30-question PDF sample are authorized.
- Production contracts forbid sample-PDF hardcoding. Company
  insufficient evidence still never falls back to world knowledge or
  Web.

## Unverified

- Extra-terms deploy, title rename, diagnostics, private gold,
  isolation, repair, live qualification, GitHub merge, leftover
  P06-17, and the frozen 30-question sample. Those belong to P06-66
  through P06-72, leftover P06-17, and the post-merge sample.

## Rollback

Delete packets 65–72, this ADR, and the deviation sections. Restore
the prior plan-integrity lock. Do not change application code.

## Handoff to P06-66

Prove the hosted term outage, deploy the reviewed seven-argument extra
terms RPC, and record live `pg_proc` plus smoke evidence. Do not
rename documents or change ranking in that packet.
