---
title: ADR — Hybrid Pilot release cut
adr_id: ADR-hybrid-pilot-release-cut
status: accepted
owner: product-owner / engineering-lead
last-reviewed: 2026-08-12
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-08-12"
audience: client-approver, engineering
decision_text: "approved"
---

# ADR: Hybrid Pilot release cut

## Status

`accepted` — framework, checkpoint dates, objective criteria, and production-label prohibition approved on 2026-08-12 via user message `approved`. Checkpoint *continue-versus-pilot decisions* themselves remain pending until each checkpoint date. Not a production authorization.

## Context

The production v1 release requires Hybrid plus LightRAG and all v1 acceptance gates. Schedule or budget pressure may force an optional prerelease labeled `0.x Hybrid Pilot` after Phases 1–4 plus the Phase-6 thin chat/streaming/budget path and a minimal Phase-8 UI.

Global contracts require a dated Hybrid Pilot decision record during Phase 1 sign-off, with checkpoints at end of Phase 1 and end of Phase 4, and objective continue-versus-pilot criteria. Silence is not approval to relabel a pilot as production.

## Decision (accepted)

1. Keep **production v1** defined as Hybrid + LightRAG + all v1 acceptance gates.
2. Treat **Hybrid Pilot** as an optional non-production cut only if objective criteria below are met and the named approver explicitly chooses it.
3. Hold two dated decision checkpoints (calendar targets derived from the plan effort ranges; adjust only with recorded approval):

| Checkpoint | Planned date | Scope | Approver field | Decision recorded |
| --- | --- | --- | --- | --- |
| End of Phase 1 | 2026-08-22 | Confirm targets/sign-off and whether the full Hybrid+Graph path remains funded | user (Cursor chat) | framework accepted 2026-08-12; checkpoint decision pending |
| End of Phase 4 | 2026-11-07 | Re-estimate delivery; choose continue-to-GraphRAG vs Hybrid Pilot cut before Phase 5 starts | user (Cursor chat) | framework accepted 2026-08-12; checkpoint decision pending |

Effort basis (one experienced FTE, excluding client wait): Phase 1 ≈1–1.5 weeks; Phases 2–4 ≈1.5–2.5 + 3–4 + 3.5–5 weeks. Dates assume work start 2026-08-12 and mid-to-upper planning ranges; they are planning anchors, not SLAs.

## Objective continue-versus-pilot criteria

At each checkpoint the approver must record a binary choice using these criteria:

| Criterion | Continue toward production v1 (Hybrid + Graph) | Choose Hybrid Pilot cut |
| --- | --- | --- |
| Phase 1 gate status | Packet 1–6 exit evidence accepted; quality/cost/capacity signed | Phase 1 incomplete or unsigned → do not start Phase 2; pilot not available as escape hatch |
| Phase 4 Hybrid gates | Hybrid latency, Recall@, citation, BM25 qualification, and cost ceilings met or formally waived via ADR | Hybrid gates fail and cannot be remediated within remaining budget/schedule |
| Revised Phase 5 estimate | Updated GraphRAG estimate still fits remaining approved calendar and budget | Phase 5 estimate exceeds remaining approved calendar or budget |
| SME availability | SME/glossary/eval labeling available for graph and Combined gates | SME unavailable for graph evaluation window |
| Approved remaining budget | Normal ceilings plus graph maintenance reserve still funded | Reserve or delivery budget insufficient for GraphRAG |
| Label honesty | Continue path remains labeled toward production v1 | Pilot must be labeled **non-production / 0.x Hybrid Pilot**; it does **not** satisfy plan v1 completion criteria |

## Explicit production-label prohibition

A Hybrid Pilot **must not** be marketed, contracted, or operated as “production v1.” Relabeling requires a new signed scope that redefines acceptance gates; it is outside this ADR.

## Consequences

- Phase 4 exit must re-estimate delivery and record the continue-versus-pilot decision before Phase 5 starts.
- Choosing the pilot reschedules GraphRAG, graph explorer, and generalized optional-tool catalog before any later production scope is redefined.
- Choosing continue commits to Phase 5+ under the signed envelopes in [QUALITY_TARGETS.md](../QUALITY_TARGETS.md).

## Approver sign-off

| Field | Value |
| --- | --- |
| Approver name | user (Cursor chat; no legal name provided) |
| Role | client / project approver (session) |
| Decision on this ADR | accept defaults |
| Approval date | 2026-08-12 |
| Notes | Exact message: `approved`. No date changes. Checkpoint continue-vs-pilot votes still due on 2026-08-22 and 2026-11-07. |

## Links

- [QUALITY_TARGETS.md](../QUALITY_TARGETS.md)
- [Global contracts](../../.cursor/plans/hybrid-graph-rag/00-global-contracts.md)
- [Phase 1 foundation evidence](../development/phase-01-foundation-evidence.md)
