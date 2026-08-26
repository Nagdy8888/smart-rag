# P06-08 narrow fix — LangSmith Studio Chat compatibility (2026-08-25)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

The completed Packet 8 developer surface had a Studio-only compatibility gap:
`query_studio` accepted an arbitrary `messages` list but exposed neither
LangGraph's typed message schema/reducer nor a terminal assistant turn. Graph
mode worked, while Studio Chat could not complete a visible exchange.

The narrow repair:

- moves `messages` out of production `QueryGraphState` and into a
  Studio-only state using `Annotated[list[AnyMessage], add_messages]`;
- accepts both LangChain message objects and Studio/OpenAI-style message
  mappings when deriving `user_query`;
- routes every Studio terminal path through `emit_studio_response`, which
  appends one `AIMessage` from verified/draft answer text or the existing safe
  status/refusal;
- preserves no paid admission, no application conversation-memory write, no
  new gateway/tool call, and no fabricated retrieval success;
- documents that the unbound Studio graph returns
  `Insufficient authorized evidence.` for document questions.

Current primary documentation was checked through Context7 library
`/websites/langchain_oss_python_langgraph`: LangGraph chat state uses
`AnyMessage` plus the `add_messages` reducer, and nodes append `AIMessage`
updates.

Verification:

- `uv run pytest tests/unit/test_query_studio.py tests/contract/test_langgraph_config.py -q`
  → 10 passed.
- `uv run pytest tests/unit/test_query_graph_runtime.py tests/unit/test_query_routing_matrix.py tests/unit/test_query_retrieve_state_sync.py tests/unit/test_query_correction.py tests/unit/test_query_branches_citations.py tests/unit/test_query_admission_ceilings.py tests/unit/test_query_studio.py tests/contract/test_langgraph_config.py -q`
  → passed (one unrelated Starlette deprecation warning).
- focused Ruff over the five changed Python/test files → passed.
- focused Pyright over the same files → 0 errors.
- live `POST http://127.0.0.1:2024/runs/wait` with
  `assistant_id=query_studio` and one `{"role":"human","content":"Hello"}`
  input returned ordered `human` then `ai` messages; the assistant content was
  the deterministic local greeting.

The local Agent Server hot-reloaded all three graph exports successfully.
Live retrieval/OpenAI binding remains intentionally unverified and unchanged.
Rollback is to remove the Studio-only message state/emitter and restore direct
Studio terminal edges to `END`; production FastAPI query execution is not
affected.
