---
title: ADR — Phase 4 engineering-complete close without SME holdout
adr_id: ADR-phase4-engineering-close
status: accepted
owner: product-owner / engineering-lead
last-reviewed: 2026-08-15
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-08-15"
audience: client-approver, engineering
decision_text: "start (engineering-close plan)"
---

# ADR: Phase 4 engineering-complete close without SME holdout

## Status

`accepted` — the project approver chose the demo engineering-close path on 2026-08-15 (`start` on the Phase 4 close plan). This is not a production v1 authorization and does not open the synthetic holdout.

## Context

Packet 8 recorded an honest **no-go**: the 405-case corpus is `synthetic_provisional`, named Knowledge Owner/SME hours were never supplied, live ranked-ID Recall@K was not measured, and holdout labels stayed sealed. The original Phase 4 `Done when` mixed retrieval gates with Phase 6 answer-token/faithfulness gates and required an independently SME-sealed holdout for phase completion.

This repository is a greenfield demo. The Cursor-chat user is the project approver. There is no separate company Knowledge Owner.

## Decision

1. **Engineering complete** may accept Phase 4 when Packet 9 proves end-to-end Hybrid retrieve plus Phase-4-owned **open-split** ranked-ID Recall@10 / exact-code Recall@5 / alias Recall@10, citation **locator** correctness, ACL negatives, table fixtures, and first-evidence p95 (QT-LAT-001), with holdout access remaining denied.
2. **Do not** open, score, or tune on the current synthetic holdout merely to produce a number.
3. A **v1 launch** still requires a newly collected, independently sealed holdout after named SME/Knowledge Owner review. Packet 8 no-go remains the holdout record until that exists.
4. First-answer-token p95, Hybrid completion p95, and answer faithfulness stay **Phase 6/9** measure-in owners.
5. Continue-versus-pilot: **continue toward GraphRAG later**. This ADR does not start Phase 5 and does not declare `0.x Hybrid Pilot` (that cut still needs Phase 6 thin chat plus a minimal Phase 8 UI).
6. Relationship, multi-hop, graph_mapping, and prompt_injection labels stay deferred and cannot make Phase 4 pass.

## Consequences

- Phase 4 wrapper `status: complete` still requires explicit user acceptance of Packet 9 evidence after the open-split gates (or an honest recorded miss).
- Combined +10 percentage-point proof remains Phase 6.
- Relabeling this close as production v1 is forbidden.

## Links

- [ADR-hybrid-pilot-release-cut.md](./ADR-hybrid-pilot-release-cut.md)
- [QUALITY_TARGETS.md](../QUALITY_TARGETS.md)
- [PHASE4_HOLDOUT.md](../evaluation/PHASE4_HOLDOUT.md)
- [phase-04-hybrid-rag-evidence.md](../development/phase-04-hybrid-rag-evidence.md)
- [docs index](../README.md)
