---
title: P06-37 advanced web research amendment
owner: engineering-lead
status: draft
last-reviewed: 2026-09-14
audience: engineering, reviewers, security
---

# P06-37 — Advanced web research amendment (2026-09-14)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Markdown-only authorization. No application code, prompt, migration,
environment default, Compose default, or `.env` value changed in this
packet.

Requirement: authorize Ask dropdown Auto / Company documents / General /
Web, Auto default, exactly-one-source Auto routing, Exa local/free-tier
only, production-disabled Web, and additive packets P06-38 through
P06-43. Integrity keeps packet numbers contiguous after P06-36 because
P06-27–36 already authorize hosted evaluation.

## Plan requirement

Quote: authorize advanced web research overlay, ADR, and packets P06-38
through P06-43.

Positive checks: ADR with Mermaid, alternatives, security, cost,
retention, rollout, rollback, and production prohibition; unique
requirement IDs P06-37–P06-43; packets 1–36 unchanged; company
insufficient evidence never falls back to web or general knowledge.

Negative checks: no Python/TypeScript/SQL/runtime JSON/env default; no
reuse of packet numbers 27–36; no optional-tool `web_search`; no
company+web blend.

## Files changed

- [ADR-advanced-web-research.md](../../adr/ADR-advanced-web-research.md)
- [`.cursor/plans/hybrid-graph-rag/00-global-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/00-global-contracts.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md)
- packet files `37`–`43` under
  [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/)
- [`.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md`](../../../.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md)
- [`.cursor/plans/hybrid-graph-rag/99-source-coverage.md`](../../../.cursor/plans/hybrid-graph-rag/99-source-coverage.md)
- [`.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json`](../../../.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json)
- [docs/README.md](../../README.md), [docs/adr/README.md](../../adr/README.md)

## Numbering deviation

The attached implementation plan numbered this overlay P06-27–33. Current
`main` already used those numbers for hosted evaluation, so the overlay
is P06-37–43. Packet contracts map 27→37, 28→38, 29→39, 30→40, 31→41,
32→42, 33→43.

## Verification

Recorded after lock refresh:

| Command | Exit |
| --- | --- |
| `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update` | 0 (199 canonical files) |
| `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | 0 (199 canonical files) |
| markdownlint-cli2 on new ADR/evidence files | 0 |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 1; pre-existing `MD012` in `p06-16-sse-custom-progress-amendment-2026-08-26.md` (not in this packet). New Web files lint clean. |

## Proven

- Packets 1–36 remain numbered and historically complete where already
  checked. P06-17/P06-18 stay unchecked.
- Company insufficient evidence still never falls back to world knowledge
  or Web.
- Web research is forbidden unless `APP_ENV=local` and
  `WEB_SEARCH_ENABLED=true`.
- Auto contract requires exactly one resolved effective mode.

## Unverified

- Docs-tier command exit until recorded below.
- Live Exa quota, paid production budget, and managed `api.exa.ai` egress.

## Rollback

Delete packets 37–43 and ADR-advanced-web-research, restore pre-amendment
global/Phase 6/index sections, and restore the previous integrity lock.

## Handoff

Next coding packet is
[P06-38](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/38-exa-rest-gateway-controlled-egress.md).
The user requested the remaining sequence in the same run.
