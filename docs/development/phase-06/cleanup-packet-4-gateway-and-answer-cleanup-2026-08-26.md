# Cleanup packet 4 — Gateway and answer cleanup (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Quoted requirement: split `gateways/model.py` into request/response types,
adapter protocol, mock adapter, gateway facade/factory, and the live
OpenAI adapter; split `query_answer/generate.py` into grounded generation,
no-retrieval generation, sanitization, and a thin public dispatcher.
Preserve lazy `gateways` exports, prompt SHA, `store=False`, call
accounting, and answer origins.

Acceptance checks:

- `generate_answer(...)` remains the public dispatcher;
- request/response models are the same objects through `gateways.model`;
- `import smart_rag_core.gateways` does not load the model facade or open
  a socket;
- mock network denial, invented-ID filtering, general-chat sanitize, and
  verifier behavior stay unchanged.

Proven:

- Types live in `gateways/model_types.py`. Protocol lives in
  `model_protocol.py`. Mock adapter lives in `mock_model.py`. Live
  multi-operation adapter lives in `openai_adapter.py` so focused
  `openai_*.py` helpers stay single-purpose. `model_gateway.py` owns
  `ModelGateway`, `create_model_gateway`, and `block_openai_network`.
- `gateways/model.py` is imports, aliases, and `__all__` only, including
  `execute_openai_*` re-exports for existing callers.
- Answer generation: `sanitize.py`, `generate_no_retrieval.py`,
  `generate_grounded.py`, and thin `generate.py`.
- Module sizes (physical lines): `model.py` 73, `model_types.py` 414,
  `model_protocol.py` 101, `mock_model.py` 402, `openai_adapter.py` 358,
  `model_gateway.py` 246, `generate.py` 113, `generate_grounded.py` 129,
  `generate_no_retrieval.py` 152, `sanitize.py` 171.

Verification:

| Command | Exit | Result |
| --- | --- | --- |
| `uv run ruff check packages/core/src/smart_rag_core/gateways packages/core/src/smart_rag_core/query_answer/generate.py packages/core/src/smart_rag_core/query_answer/generate_grounded.py packages/core/src/smart_rag_core/query_answer/generate_no_retrieval.py packages/core/src/smart_rag_core/query_answer/sanitize.py tests/unit/test_model_gateway.py` | 0 | clean |
| `uv run pytest tests/unit/test_model_gateway.py tests/unit/test_openai_rerank.py tests/unit/test_general_chat_gateway.py tests/unit/test_general_chat_generate.py` | 0 | passed |
| `uv run pytest tests/unit/test_answer_verifier.py tests/unit/test_answer_filter_invented.py tests/unit/test_langsmith_tracing.py tests/unit/test_prompt_registry.py` | 0 | passed |
| `uv run pytest tests/contract/test_import_boundaries.py tests/contract/test_docstrings.py tests/unit/test_query_profile_gateway.py tests/unit/test_openai_lightrag.py tests/unit/test_package_imports.py` | 0 | passed |

Unverified: live OpenAI Responses quality; `pnpm check:fast`.

Deviations: LightRAG unit tests now patch
`smart_rag_core.gateways.openai_adapter.execute_openai_lightrag_llm`
because the live adapter binds that helper in its own module. Public
`gateways.model.execute_openai_lightrag_llm` remains.

Rollback: restore the `model.py` / `generate.py` monoliths and the
previous LightRAG patch path.

Handoff to cleanup packet 5: split `live_runtime.py`, Studio modules,
and query persistence; prove compile reuse or record the LangGraph
blocker.
