---
title: P06-58 general Hybrid retrieval accuracy amendment
owner: engineering-lead
status: draft
last-reviewed: 2026-09-17
audience: engineering, reviewers, security
---

# P06-58 — General Hybrid retrieval accuracy amendment (2026-09-17)

Parent index:
[phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Markdown-only authorization. No application code, prompt, migration,
environment default, Compose default, or `.env` value changed in this
packet.

Requirement IDs: `P06-58` through `P06-64`.

## Plan requirement

Quote: authorize general Hybrid retrieval accuracy overlay, ADR, and
packets P06-59 through P06-64.

Positive checks: ADR with Mermaid, alternatives, security, rollback,
and contiguous numbering after live-failure packets 49–57; unique
requirement IDs P06-58–P06-64; packets 1–57 unchanged; production
contracts forbid sample-PDF hardcoding; company insufficient evidence
never falls back to web or general knowledge.

Negative checks: no Python/TypeScript/SQL/runtime JSON/env default; no
reuse of packet numbers 49–57; no P06-17/P06-18/Phase 6 complete; no
holdout.

## Files changed

- [ADR-hybrid-retrieval-accuracy.md](../../adr/ADR-hybrid-retrieval-accuracy.md)
- [`.cursor/plans/hybrid-graph-rag/00-global-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/00-global-contracts.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md)
- packet files `58`–`64` under
  [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/)
- [`.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md`](../../../.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md)
- [`.cursor/plans/hybrid-graph-rag/99-source-coverage.md`](../../../.cursor/plans/hybrid-graph-rag/99-source-coverage.md)
- [`.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json`](../../../.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json)
- [docs/README.md](../../README.md), [docs/adr/README.md](../../adr/README.md)

## Numbering and branch base

P06-49 through P06-57 already authorize live RAG failure remediation.
Integrity requires contiguous packet numbers, so this overlay is
P06-58 through P06-64 on `fix/general-rag-retrieval-accuracy` from
current `main`.

## Verification

| Command | Exit |
| --- | --- |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update` | 0 (220 canonical files) |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | 0 (220 canonical files) |
| `uv run python scripts/check.py --tier docs` | 0 |
| `git diff --check` | 0 |

## Proven

- Packets 1–57 remain numbered. P06-45 through P06-48 stay unchecked.
  P06-17 and P06-18 stay unchecked. Phase 6 stays incomplete.
- Dual-metric scoring, authorized source resolution, ranking-query
  title stripping, post-ACL exact-duplicate collapse, term/BM25
  candidate repair, retrieve-time accounting, a measured long-document
  profile, and coverage/correction repair are authorized.
- Production contracts forbid sample-PDF hardcoding. Company
  insufficient evidence still never falls back to world knowledge or
  Web.

## Unverified

- Dual-metric runner, source ranking, candidate repair, accounting,
  coverage/correction, live qualification, and leftover P06-17. Those
  belong to P06-59 through P06-64 and P06-17.

## Rollback

Delete packets 58–64, this ADR, and the deviation sections. Restore
the prior plan-integrity lock. Do not change application code.

## Handoff to P06-59

Create the tested private-safe dual-metric scorer and stage
attribution baseline. Do not change retrieval ranking in that packet.
