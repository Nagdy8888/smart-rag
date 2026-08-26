# Cleanup packet 1 — Governance, inventory, and baseline (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Quoted requirement: confirm BR-1A through BR-3 are accepted, mark the
older brain-repair plan superseded, confirm amended packets authorize
explicit scope nodes, and record module sizes, cycle guards, compile
counts, visited nodes, and mocked route timings. No production Python
changes.

Acceptance checks:

- BR-1 through BR-3 remain evidenced;
- older brain-repair plan stays superseded;
- module sizes and cycle-guard locations are recorded;
- `compile_query_graph` compile count and mocked scope-route timings
  are recorded;
- focused governance/import/docstring/LangGraph suites stay green.

Proven:

- Baseline written at
  [phase-06-query-agent-cleanup-baseline.md](../phase-06-query-agent-cleanup-baseline.md).
- `pipeline.py` was 1847 lines / 31 symbols before packet 2.
- First `compile_query_graph()` 9.3 ms; second 12.4 ms; no process cache.
- Hello/France → `general_scope`; refund → `company_scope`; mixed →
  `mixed_scope`.
- `verify_plan_integrity.py` still reports 107 canonical files.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run python scripts/verify_plan_integrity.py` | 0 | 107 canonical files |
| focused governance / import / docstring / LangGraph registration | 0 | 19 passed |

Unverified: `pnpm check:fast` was not re-run in this continuation.

Deviations: none. Production Python was not edited in this packet.

Rollback: delete the baseline document and its docs-index row.

Handoff to cleanup packet 2: replace `nodes/pipeline.py` with cohesive
node modules and gateway helpers.
