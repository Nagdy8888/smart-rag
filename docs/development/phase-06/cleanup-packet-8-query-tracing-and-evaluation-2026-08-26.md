# Cleanup packet 8 — Query tracing and evaluation (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Quoted requirement: split query-run tracing into redaction, SSE tracing,
agent-eval tracing, and metadata; split agent evaluation into schemas,
case mapping, deterministic scorers, and LangSmith registration; split
the LangSmith agent-evaluation CLI into argument/configuration and
live-run modules; keep redaction, cost fields, prompt versions, online
envelope bounds, and evaluator registry identity unchanged.

Acceptance checks:

- public `query_run_trace` and `evaluation.agent_eval` imports resolve;
- evaluator names, feedback keys, and frozen-fixture scores unchanged;
- redacted trace payloads still omit secrets/passages;
- CLI command surface `--dry-run --limit 3` is unchanged;
- Phase 6 eval registry check still passes.

Proven:

- Package `observability/query_trace/` with `redaction.py`, `metadata.py`,
  `sse.py`, and `agent_eval.py`. `query_run_trace.py` is a re-export
  facade and still exports `traceable` / `tracing_is_enabled`.
- Package `evaluation/agent_eval/` with `schema.py`, `mapping.py`,
  `scorers.py`, and `langsmith.py`. The former `agent_eval.py` file was
  removed so the package can own the name.
- CLI helpers live under `evaluation/agent_eval_cli/` (`config.py`,
  `runtime.py`, `main.py`). `scripts/eval_query_agent_langsmith.py`
  remains the documented entrypoint.

Module sizes (physical lines): query_trace `redaction` 354, `metadata`
217, `sse` 185, `agent_eval` 234, facade 43; agent_eval `schema` 290,
`mapping` 537, `scorers` 346, `langsmith` 211, package `__init__` 95;
CLI `config` 132, `runtime` 407, `main` 235, script 22.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run pytest tests/unit/test_query_run_sse_trace.py tests/unit/test_query_agent_eval_trace.py tests/unit/test_langsmith_tracing.py tests/unit/test_agent_eval.py tests/unit/test_langsmith_agent_runner.py tests/unit/test_langsmith_online_evaluator.py tests/unit/test_phase6_eval_registry.py -q` | 0 | passed |
| `uv run python scripts/ci/check_phase6_eval_registry.py` | 0 | clean |
| `uv run python scripts/eval_query_agent_langsmith.py --dry-run --limit 3` | 0 | `holdout_opened=false`, 3 development cases, dataset name unchanged |

Unverified: hosted `--online-only` live write path (not required for this
structural packet). Dry-run online path remains covered by unit tests.

Deviations: online-eval tests now patch
`query_trace.agent_eval.traceable` / `tracing_is_enabled` because those
names are bound in the lifecycle module. CLI live-run is split into
`runtime.py` plus `main.py` so no CLI module exceeds 600 lines.

Rollback: restore `query_run_trace.py` and `evaluation/agent_eval.py`
monoliths and the single-file CLI.

Handoff to cleanup packet 9: split oversized tests/evidence, add the
architecture scanner, remove proven dead code, and update routing/docs
indexes.
