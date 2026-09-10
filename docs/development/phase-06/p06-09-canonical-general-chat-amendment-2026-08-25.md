# P06-09 — Canonical general-chat amendment (2026-08-25)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Original strict-split amendment. The 2026-08-26 remediation was accepted
2026-09-10 by the user in Cursor chat.

Markdown-only amendment. No application code, prompt, migration, or graph
registration changed in this packet.

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
| `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update` | recorded with overlay lock refresh |
| `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | recorded with overlay lock refresh |

Proven: wrapper Packet 9 is checked, ADR `amendment_approval_date=2026-09-10`,
and company insufficient evidence still never falls back to general
knowledge.

Unverified: none for this markdown packet.

Rollback: restore Packet 9 to pending, revert the 2026-09-10 acceptance
dates, and restore the previous integrity lock.

Handoff: overlay packets P06-19 through P06-26 execute before Packet 10.
