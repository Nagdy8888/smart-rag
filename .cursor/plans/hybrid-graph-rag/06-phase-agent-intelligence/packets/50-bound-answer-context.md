---
phase: 6
packet: 50
status: complete
title: "Implement deterministic evidence fitting, exact duplicate suppression, typed overflow handling, and answer/deadline reserves with Q15 regressions."
requirement_ids: [P06-50]
---

# Packet 50 — Implement deterministic evidence fitting, exact duplicate suppression, typed overflow handling, and answer/deadline reserves with Q15 regressions.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md).

Do not load frontend, FastAPI-router, or Supabase-migration skills.

## Preconditions

- P06-49 is recorded. Branch is `fix/rag-reliability-and-citations`.
- Q15 overflow is proven: nine passages, 18,683 raw characters,
  `MODEL_INPUT_MAX_CHARS=16384`, `answer_calls=0`, SSE `empty_answer`.
- Inspect `assembly.py`, `gateway/answer.py`, `nodes/answer.py`,
  `sync_bridge.py`, `deps.py`, `deps_factory.py`, and current tests
  before editing.

## Allowed outputs

- `packages/core/src/smart_rag_core/query_answer/assembly.py`
- `packages/core/src/smart_rag_core/query_answer/models.py`
- `packages/core/src/smart_rag_core/gateways/openai_adapter.py`
- `packages/core/src/smart_rag_core/gateways/mock_model.py`
- `apps/agents/src/smart_rag_agents/query/gateway/answer.py`
- `apps/agents/src/smart_rag_agents/query/gateway/sync_bridge.py`
- `apps/agents/src/smart_rag_agents/query/nodes/answer.py`
- `apps/agents/src/smart_rag_agents/query/deps.py`
- `apps/agents/src/smart_rag_agents/query/runtime/deps_factory.py`
- Admission/ceiling modules that already own company call/deadline
  reserves
- `tests/unit/test_answer_source_assembly_budget.py` (new)
- `tests/unit/test_query_graph_runtime.py`
- `tests/unit/test_query_admission_ceilings.py`
- Packet evidence under `docs/development/phase-06/`
- Docs that already describe answer assembly / budgets

## Forbidden outputs

- Raising `MODEL_INPUT_MAX_CHARS`.
- Fuzzy duplicate dropping, truncating passages, or splitting tables.
- Collapsing `ModelInputBoundError` into `gateway_failed`.
- Spending the two-call/eight-second reserve on retrieval/correction.
- Applying company reserve logic to general, user-text, or Web.
- SQL, OpenAPI, frontend, prompt-file, or Compose changes.
- Starting Packet 51 grounded-release work.

## Ordered actions

1. Add frozen `SourceAssemblyFit` and pure `fit_source_records` in
   `assembly.py`. No model/DB/token estimation inside the function.
2. Validate `max_input_chars >= 1`. Count delimiter overhead. Iterate
   fusion order. Drop later normalized-exact duplicates. Retain a
   whole block only when the joined request stays in bound.
3. For StructuredTable/Composite, reserve the complete table block
   before optional lower-ranked prose. Hybrid/Combined stay
   passage-first. Route is server-derived.
4. Return ID/count diagnostics only. Never serialize source text.
5. Pass the fitted subset through answer, verify, and citations.
   Dropped IDs must not appear in the model request or citations.
6. Add `ModelInputBoundError`. Mock and OpenAI adapters raise it.
   `run_coro` maps the type to `AnswerError("input_bound_exceeded")`
   without inspecting exception strings.
7. Add `ANSWER_STAGE_RESERVED_MODEL_CALLS = 2` and
   `ANSWER_STAGE_MIN_SECONDS = 8.0`. If remaining wall time is under
   eight seconds, return `answer_deadline_reserve_exhausted` with
   non-empty refusal and zero provider attempts. Inject a fake clock.
8. If no complete block fits, nodes/answer returns the canonical
   refused payload named in the ADR.

## Acceptance checks

- Nine Q15-sized passages fit to `len(query + records) <= 16384`.
- The fake gateway is called once with bounded records and non-zero
  synthetic completion usage.
- Two identical normalized texts retain only the higher-ranked ID.
- Near-but-not-identical text is retained.
- Fitting is deterministic and does not mutate the original fusion
  result.
- Dropped IDs cannot be cited.
- An impossibly small budget yields typed non-empty refusal, never
  `gateway_failed` or `empty_answer`.
- Two calls and eight seconds remain for answer/verification.
- Reserve exhaustion skips the provider.

## Negative tests

- Truncating a passage to fill leftover bytes fails the packet.
- Fuzzy-dropping distinct evidence fails the packet.
- Mapping overflow to `gateway_failed` fails the packet.
- Sleeping eight seconds in tests fails the packet.

## Stop routes

- Stop if fitting would require raising the model input bound.
- Stop if company answers would skip canonical retrieval to save the
  reserve.
- Do not start Packet 51 prompt or verifier work.

## Required evidence

- New unit file, ruff, pyright, pytest exits, and Q15 synthetic proof.
- Commands:

  ```powershell
  uv run python -m pytest tests/unit/test_answer_source_assembly_budget.py tests/unit/test_query_graph_runtime.py tests/unit/test_query_admission_ceilings.py tests/unit/test_query_sse_mapping.py -q
  uv run ruff check packages/core/src/smart_rag_core/query_answer apps/agents/src/smart_rag_agents/query tests/unit/test_answer_source_assembly_budget.py tests/unit/test_query_graph_runtime.py tests/unit/test_query_admission_ceilings.py
  uv run pyright packages/core/src/smart_rag_core/query_answer apps/agents/src/smart_rag_agents/query
  git diff --check
  ```

- Commit `fix(rag): bound answer context and preserve answer budget`.
