---
title: P06-44 PDF paragraph-citation amendment
owner: engineering-lead
status: draft
last-reviewed: 2026-09-15
audience: engineering, reviewers, security
---

# P06-44 — PDF paragraph-citation amendment (2026-09-15)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Markdown-only authorization. No application code, prompt, migration,
environment default, Compose default, or `.env` value changed in this
packet.

Requirement IDs: `P06-44`, `CIT-PAGE-001`, `CIT-TITLE-002`,
`CIT-PARA-003`, `CIT-SPAN-004`, `CIT-ACL-008`, `CIT-COMPAT-011`.

## Plan requirement

Quote: authorize PDF paragraph-citation overlay, ADR, and packets
P06-45 through P06-48.

Positive checks: ADR with Mermaid, alternatives, security, excerpt
cap, rollback, and PDF viewer page semantics; unique requirement IDs
P06-44–P06-48; packets 1–43 unchanged; company insufficient evidence
never falls back to web or general knowledge.

Negative checks: no Python/TypeScript/SQL/runtime JSON/env default; no
reuse of packet numbers 37–43; no `page_label` as the chat page; no
full-chunk or SSE excerpt disclosure.

## Files changed

- [ADR-pdf-paragraph-citations.md](../../adr/ADR-pdf-paragraph-citations.md)
- [`.cursor/plans/hybrid-graph-rag/00-global-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/00-global-contracts.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md)
- packet files `44`–`48` under
  [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/)
- [`.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md`](../../../.cursor/plans/hybrid-graph-rag_ab5281ef.plan.md)
- [`.cursor/plans/hybrid-graph-rag/99-source-coverage.md`](../../../.cursor/plans/hybrid-graph-rag/99-source-coverage.md)
- [`.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json`](../../../.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json)
- [docs/README.md](../../README.md), [docs/adr/README.md](../../adr/README.md)

## Numbering and branch base

`origin/main` still lacks P06-37–43. Integrity requires contiguous
packet numbers, so this overlay is P06-44–48 on a worktree created from
committed `feature/advanced-web-research-mode` HEAD
(`f456765`). Dirty P06-41 frontend files remain in the original
worktree. Snapshot:
`refs/backup/pre-citation-split-20260915132925`.

## Verification

Recorded after lock refresh:

| Command | Exit |
| --- | --- |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update` | 0 (204 canonical files) |
| `uv run python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | 0 (204 canonical files) |
| `pnpm exec markdownlint-cli2 docs/**/*.md` | 1; pre-existing `MD012` in `p06-16-sse-custom-progress-amendment-2026-08-26.md`. New citation files lint clean. |
| `uv run python scripts/check_docs.py --puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | 0 after correcting the P06-37 evidence index link `../README.md` to `../../README.md` |

## Proven

- Packets 1–43 remain numbered. P06-42/P06-43 and P06-17/P06-18 stay
  unchecked.
- Chat page is the 1-based PDF viewer file page.
- Excerpt disclosure is capped at 1000 characters after live ACL
  recheck.
- Company insufficient evidence still never falls back to world
  knowledge or Web.

## Unverified

- Full `scripts/check.py --tier docs` still fails on pre-existing `MD012`
  in `p06-16-sse-custom-progress-amendment-2026-08-26.md`.
- Live PDF evaluation ≥98% citation correctness.

## Rollback

Delete packets 44–48 and ADR-pdf-paragraph-citations, restore
pre-amendment global/Phase 6/index sections, and restore the previous
integrity lock.

## Handoff

Next coding packet is
[P06-45](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/45-pdf-paragraph-grounding.md).
The user requested the remaining sequence in the same run.
