---
title: P06-49 live RAG failure remediation amendment
owner: engineering-lead
status: draft
last-reviewed: 2026-09-16
audience: engineering, reviewers, security
---

# P06-49 — Live RAG failure remediation amendment (2026-09-16)

Parent index:
[phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Markdown-only authorization. No application code, prompt, migration,
environment default, Compose default, or `.env` value changed in this
packet.

Requirement IDs: `P06-49` through `P06-57`.

## Plan requirement

Quote: authorize live RAG failure remediation overlay, ADR, and
packets P06-50 through P06-57.

Positive checks: ADR with Mermaid, alternatives, security, rollback,
and contiguous numbering after PDF packets 44–48; unique requirement
IDs P06-49–P06-57; packets 1–48 unchanged; company insufficient
evidence never falls back to web or general knowledge.

Negative checks: no Python/TypeScript/SQL/runtime JSON/env default; no
reuse of packet numbers 44–48; no P06-17/P06-18/Phase 6 complete; no
holdout.

## Files changed

- [ADR-live-rag-failure-remediation.md](../../adr/ADR-live-rag-failure-remediation.md)
- [`.cursor/plans/hybrid-graph-rag/00-global-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/00-global-contracts.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md)
- packet files `49`–`57` under
  [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/)
- [`.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md`](../../../.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md)
- [`.cursor/plans/hybrid-graph-rag/99-source-coverage.md`](../../../.cursor/plans/hybrid-graph-rag/99-source-coverage.md)
- [`.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json`](../../../.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json)
- [docs/README.md](../../README.md), [docs/adr/README.md](../../adr/README.md)

## Numbering and branch base

P06-44 through P06-48 already authorize PDF paragraph citations,
including `answer_v2.md` and `app.list_conversation_messages_v2`.
Integrity requires contiguous packet numbers, so this overlay is
P06-49 through P06-57 on `fix/rag-reliability-and-citations` from
merged `main` (`8044b937`). New prompt pins are `answer_v3` and
`verifier_v2`. New transcript RPC is
`app.list_conversation_messages_v3`.

## Verification

| Command | Exit |
| --- | --- |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update` | 0 (213 canonical files) |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | 0 (213 canonical files) |
| `uv run python scripts/check.py --tier docs` | 0 after this evidence file existed |
| `git diff --check` | 0 |

## Proven

- Packets 1–48 remain numbered. P06-45 through P06-48 stay unchecked.
  P06-17 and P06-18 stay unchecked. Phase 6 stays incomplete.
- Exact duplicate suppression, whole-block fitting, two-call/eight-second
  reserves, grounded release, graceful terminals, additive transcript
  metadata, reload restore, Postgres reconnect, and host-worker/Exa
  lifecycle are authorized.
- Company insufficient evidence still never falls back to world
  knowledge or Web.

## Unverified

- Live Q15/Q3 repair, transcript v3 migration application, host-worker
  start/stop, and leftover P06-17 qualification. Those belong to
  P06-50 through P06-57.

## Rollback

Delete packets 49–57 and ADR-live-rag-failure-remediation, restore
pre-amendment global/Phase 6/index sections, and restore the previous
integrity lock.

## Handoff

Next coding packet is
[P06-50](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/50-bound-answer-context.md).
The user requested the remaining sequence in the same run.
