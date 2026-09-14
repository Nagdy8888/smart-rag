---
title: P06-27 hosted webapp evaluation amendment
owner: engineering-lead
status: draft
last-reviewed: 2026-09-10
audience: engineering, reviewers, security
---

# P06-27 — Hosted webapp evaluation amendment (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Markdown-only authorization. No application code, prompt, migration,
environment default, Compose default, frozen Hybrid profile, or hosted
mutation changed in this packet.

Requirement: supersede local-file-only custody, record hosted 365-day
quiz/exam custody, production-corpus Hybrid Recall@10, feedback coexistence,
holdout/freeze exclusion, and additive packets P06-28 through P06-36.
Integrity keeps packet numbers contiguous after P06-26. Execution after
this packet: accept P06-27, then existing Packet 10, then P06-28 through
P06-36, then P06-11.

## Plan requirement

Quote: authorize the hosted-evaluation workspace amendment, ADR, and packets
P06-28 through P06-36.

Positive checks: old no-table decision superseded; hosted 365-day custody
and production-corpus metric explicit; feedback coexistence; holdout
exclusion; qualification one-shot; rollback; P06-10 dependency; Packet 10
file/title unchanged; integrity and docs links pass.

Negative checks: no Python/TypeScript/SQL/runtime JSON/env default; do not
mark managed region/DPA/backup verified; do not start P06-10 or P06-28.

## Files changed

- [ADR-hosted-webapp-evaluation-workspace.md](../../adr/ADR-hosted-webapp-evaluation-workspace.md)
- [ADR-local-pdf-evaluation-workspace.md](../../adr/ADR-local-pdf-evaluation-workspace.md) (superseded)
- [`.cursor/plans/hybrid-graph-rag/00-global-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/00-global-contracts.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md)
- packet files `27`–`36` under
  [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/)
- [`.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md`](../../../.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md)
- [`.cursor/plans/hybrid-graph-rag/99-source-coverage.md`](../../../.cursor/plans/hybrid-graph-rag/99-source-coverage.md)
- [`.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json`](../../../.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json)
- docs indexes, governance residual-risk note, configuration intent,
  evaluation/admin/authorization/quality/data-dictionary pointers

## Residual-risk exception

Managed Supabase region, backup, subprocessors, and DPA rows in
[SUBPROCESSOR_GOVERNANCE.md](../../security/SUBPROCESSOR_GOVERNANCE.md)
remain **unverified**. This packet records a named 2026-09-10 residual-risk
exception for quiz/exam rows in the existing hosted project. It does not
set those matrix rows to verified and does not authorize staging/production
evaluation UI.

## Verification

Recorded after lock refresh:

| Command | Exit |
| --- | --- |
| `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update` | 0 (192 canonical files) |
| `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | 0 (192 canonical files) |
| `pnpm check:docs` | 0 |

## Proven

- Packets 19–26 remain checked. Packet 10 number and title are unchanged.
- Company insufficient evidence still never falls back to world knowledge.
- Holdout remains outside the hosted workspace contract.
- Ordinary thumbs feedback remains a product workflow.

## Unverified

- Live Packet 10 acceptance and P06-28 hosted migration apply.
- Managed region/DPA/backup verification.
- Any Recall@10 number.

## Rollback

Delete packets 27–36 and ADR-hosted-webapp-evaluation-workspace, restore the
local-file ADR to accepted, restore pre-amendment global/Phase 6/index
sections, and restore the previous integrity lock.

## Handoff

Next coding packet is existing
[P06-10](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/10-knowledge-scope-routing.md).
Do not start P06-28 until Packet 10 is accepted. Explicit user acceptance of
this P06-27 markdown packet is required before that coding run.
