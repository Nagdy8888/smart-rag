# P06-09 — Canonical general-chat amendment (2026-08-25)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Original strict-split amendment. The 2026-08-26 remediation below is drafted
and pending explicit user acceptance; this 2026-08-25 record remains the
accepted baseline until that acceptance is recorded.

Markdown-only amendment. No application code, prompt, migration, or graph
registration changed.

Requirement: record the approved strict-split deviation, ADR, and additive
Phase 6 packets P06-10 through P06-15. P06-14 is a Phase 6/Phase 8 co-owned
UI amendment. Historical Phase 6 packets 1–8 and Phase 8 packet numbers
remain unchanged.

Files:

- [`.cursor/plans/hybrid-graph-rag/00-global-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/00-global-contracts.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md)
- [`.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration.md`](../../../.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration.md)
- [`.cursor/plans/hybrid-graph-rag/99-source-coverage.md`](../../../.cursor/plans/hybrid-graph-rag/99-source-coverage.md)
- [`.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json`](../../../.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json)
- packet files `09`–`15` under
  [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/)
- [`docs/adr/ADR-general-chat-strict-split.md`](../../adr/ADR-general-chat-strict-split.md)
- [`docs/README.md`](../../README.md)
- [`docs/adr/README.md`](../../adr/README.md)

Verification:

| Command | Exit |
| --- | --- |
| `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update` | 0 (107 canonical files) |
| `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | 0 |
| `pnpm exec markdownlint-cli2 docs/adr/ADR-general-chat-strict-split.md docs/README.md docs/adr/README.md` | 0 |
| `uv run python scripts/check_docs.py` | 0 (elapsed 254191 ms) |

Proven: wrapper/packet titles match, reciprocal ADR/index links resolve, Phase 8
does not renumber P08-22/P08-23, and P06-10 is the next coding packet.

Unverified: none for this markdown packet.

Rollback: delete the new packet files and ADR, revert the deviation/index
sections, and restore the previous integrity lock.

Handoff to P06-10: implement typed `KnowledgeScope` classification and
deterministic NoRetrieval mode mapping without touching answer generation,
Studio live, SSE lifecycle, or frontend code.
