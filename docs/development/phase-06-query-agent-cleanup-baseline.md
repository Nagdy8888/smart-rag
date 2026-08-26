---
title: Query-agent cleanup structural baseline
owner: engineering-lead
status: draft
last-reviewed: 2026-08-26
audience: engineering, reviewers
phase_packet: Cleanup packet 1
---

# Query-agent cleanup structural baseline

Recorded after BR-1 through BR-3 and before structural cleanup packets 2–9.
This packet changes no production Python.

Related: [phase-06-agent-intelligence-evidence.md](./phase-06-agent-intelligence-evidence.md) ·
[QUERY_ROUTING.md](../agent/QUERY_ROUTING.md) ·
[scope_graph_nodes_916779e1.plan.md](../../.cursor/plans/scope_graph_nodes_916779e1.plan.md) ·
[docs index](../README.md)

## Governance

- BR-1A/B/C, BR-2, and BR-3 are evidenced and accepted in this session.
- [agent_brain_repair_8c84c1f7.plan.md](../../.cursor/plans/agent_brain_repair_8c84c1f7.plan.md)
  remains `status: superseded` by the master plan.
- Amended P06-10/P06-12 authorize explicit company/general/mixed/invalid
  scope nodes and later structural cleanup. Route families and
  `company_claim_forbidden` stay unchanged.

## Module sizes (2026-08-26)

| Module | Lines | Top-level symbols |
| --- | ---: | ---: |
| `query/nodes/pipeline.py` | 1847 | 31 |
| `query/graph.py` | 603 | 8 |
| `query/live_runtime.py` | 801 | 16 |
| `query/studio.py` | 424 | 14 |
| `query/studio_live.py` | 830 | 17 |
| `query_routing/branches.py` | 1187 | 24 |
| `query_routing/matrix.py` | 676 | 11 |
| `query_routing/models.py` | 530 | 12 |
| `gateways/model.py` | 1721 | 26 |
| `query_answer/generate.py` | 540 | 11 |
| `services/sse_stream.py` | 1773 | 14 |
| `query_admission/service.py` | 904 | 19 |
| `retrieval/hybrid_run.py` | 1704 | 38 |

## Import-cycle guards

`# isort: off` + `hybrid_run` cycle guards remain in:

- `apps/agents/src/smart_rag_agents/query/graph.py`
- `apps/agents/src/smart_rag_agents/query/deps.py`
- `apps/agents/src/smart_rag_agents/query/live_runtime.py`
- `apps/agents/src/smart_rag_agents/query/nodes/pipeline.py` (removed in packet 2; guards moved to `nodes/shared.py`, `nodes/admission.py`, `nodes/prepare.py`, `nodes/answer.py`, `nodes/verify.py`, and `nodes/__init__.py`)

Cleanup packet 3 may remove them only after cold-import tests prove they
are unnecessary.

## Graph compile and mocked route timings

Local Windows measurement, mock/deterministic preparation only. Not a
release SLO.

| Metric | Value |
| --- | --- |
| `compile_query_graph()` first call | 9.3 ms |
| `compile_query_graph()` second call | 12.4 ms |
| Compilation count per call | 1 (no process cache) |
| Greeting plan → `general_scope` | 1.3 ms |
| Capital-of-France plan → `general_scope` | 0.8 ms |
| Company refund plan → `company_scope` | 0.7 ms |
| Mixed plan → `mixed_scope` | 0.8 ms |

Visited production nodes after BR-3:

`enforce_admission`, `load_memory`, `prepare_query`, `compile_plan`,
`company_scope` or `general_scope` or `mixed_scope` or `invalid_scope`,
then company-only `apply_correction` / `fuse_evidence` / `compose_tables` /
`disclose_optional_tools` / `generate_answer`, then `verify_answer`.

Heartbeat writers, retrieval/model/tool call ledgers, and SSE persistence
are unchanged from the Phase 6 evidence file. Packet 6 owns heartbeat
deduplication.

## Architecture scanner

No new CI architecture gate was added in this packet. Existing import-boundary
and docstring contracts remain the enforcement.
