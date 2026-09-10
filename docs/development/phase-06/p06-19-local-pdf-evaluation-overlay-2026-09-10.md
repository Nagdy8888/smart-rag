# P06-19 — Local PDF evaluation overlay (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Markdown-only overlay authorization. No application code, prompt, migration,
environment default, or frozen Hybrid profile changed in this packet.

Requirement: record the accepted local-only evaluation workspace ADR and
additive packets P06-20 through P06-26. Integrity keeps packet numbers
contiguous after P06-18. User-approved execution is immediately after Packet
9, then Packet 10.

Files:

- [`.cursor/plans/hybrid-graph-rag/00-global-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/00-global-contracts.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence.md)
- [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/00-shared-contracts.md)
- packet files `19`–`26` under
  [`.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/`](../../../.cursor/plans/hybrid-graph-rag/06-phase-agent-intelligence/packets/)
- [`.cursor/plans/hybrid-graph-rag/99-source-coverage.md`](../../../.cursor/plans/hybrid-graph-rag/99-source-coverage.md)
- [`.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json`](../../../.cursor/plans/hybrid-graph-rag/plan-integrity-lock.json)
- [`docs/adr/ADR-local-pdf-evaluation-workspace.md`](../../adr/ADR-local-pdf-evaluation-workspace.md)
- [`docs/README.md`](../../README.md)
- [`docs/adr/README.md`](../../adr/README.md)
- [`docs/development/hybrid-pdf-accuracy-remediation.md`](../hybrid-pdf-accuracy-remediation.md)
- [`docs/evaluation/PDF_HYBRID_EVALUATION.md`](../../evaluation/PDF_HYBRID_EVALUATION.md)

Verification:

| Command | Exit |
| --- | --- |
| `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py` | recorded after lock refresh |
| `python .cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py --update` | recorded after lock refresh |
| `uv run python scripts/check.py --tier docs --mermaid-puppeteer-config scripts/ci/puppeteer-no-sandbox.json` | recorded after lock refresh |

Proven: Packet 9 is accepted; overlay packets 19–26 are linked; Packet 10
title and number are unchanged; company insufficient evidence still never
falls back to world knowledge; holdout remains outside the workspace.

Unverified: live operator reseal, Combined +10pp, and holdout remain later
overlay/operator gates. Heading reingest is recorded on P06-23.

Rollback: delete overlay packets 19–26 and the ADR, restore Packet 9-era
deviation sections, and restore the previous integrity lock.

Handoff: Packet 20 implements the local private-file store and source-bound
draft generation. No FastAPI or frontend in Packet 20.
