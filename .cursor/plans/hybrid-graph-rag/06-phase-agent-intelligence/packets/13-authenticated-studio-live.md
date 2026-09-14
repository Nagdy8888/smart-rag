---
phase: 6
packet: 13
status: complete
title: "Add authenticated query_studio_live with per-run resources and normal ACL, admission, and budget controls."
requirement_ids: [P06-13]
---

# Packet 13 — Add authenticated query_studio_live with per-run resources and normal ACL, admission, and budget controls.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md),
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md),
and
[`implement-supabase-security`](../../../../../.cursor/skills/implement-supabase-security/SKILL.md).

## Preconditions

- Packets 10–12 have typed scope, general-answer execution, and the preserved
  Studio chat `messages` / `emit_studio_response` surface.
- `apps/agents` must not import `smart_rag_api`, FastAPI, or worker code.
  `packages/core` must not import any app package. Backend may import
  agents/core.
- Verify the pinned LangGraph Agent Server graph-factory signature from
  current primary documentation before writing `make_graph`.

## Allowed outputs

- Additive `AgentSettings` fields `LANGGRAPH_STUDIO_LIVE_ENABLED` and
  `LANGGRAPH_STUDIO_ACCESS_TOKEN`.
- New agents modules `live_runtime.py` and `studio_live.py`.
- Core `profile_snapshot.py` extracted from backend profile-loader logic.
- Mutually exclusive `studio_local` / `studio_live` modes on
  `build_query_graph`.
- Separate `query_studio_live` registration in `apps/agents/langgraph.json`.
- `.env.example` and configuration-doc mentions of the two variables.
- Tests named in Acceptance checks.

## Forbidden outputs

- Changing the existing `query_studio` registration or making it live.
- Import cycles: agents → backend, core → app packages.
- A service-role variable or synthetic `AuthorizedRuntimeContext`.
- Making `AgentSettings` inherit `BackendSettings`.
- Claiming live success without a real JWT and services.
- Printing the access token in docs, logs, traces, checkpoints, or schemas.

## Ordered actions

1. Extend inspected `AgentSettings` with:

   ```python
   langgraph_studio_live_enabled: bool = Field(
       default=False,
       validation_alias="LANGGRAPH_STUDIO_LIVE_ENABLED",
   )
   langgraph_studio_access_token: SecretStr | None = Field(
       default=None,
       validation_alias="LANGGRAPH_STUDIO_ACCESS_TOKEN",
   )
   ```

   Default disabled. Enabled without token fails execution safely. Token never
   appears in repr, state, configurable, logs, checkpoints, schemas, traces,
   or exception text. During a real live execution, load `AgentSettings` for
   the enable flag/token and load existing core `BackendSettings` separately
   for Supabase URL/JWT audience/DB DSNs/cache/runtime values.
2. Move only reusable, FastAPI-independent query-binding code into
   `apps/agents/src/smart_rag_agents/query/live_runtime.py`. Expose
   process-level Hybrid/graph/table/model/prompt bindings,
   `open_run_app_api_connection`, and
   `build_query_graph_deps(..., connection, cancel_check, store_get, store_put)`.
   Backend remains a thin wrapper. Move pure profile/JWT snapshot logic into
   `packages/core/src/smart_rag_core/security/profile_snapshot.py` and
   re-export it from backend.
3. Add `studio_live.py` exporting an async context-manager graph factory with
   the exact Agent Server signature verified from current docs and pinned
   runtime:

   ```python
   @asynccontextmanager
   async def make_graph(runtime: ServerRuntime) -> AsyncIterator[StudioCompiledGraph]:
       ...
   ```

   If `runtime.execution_runtime is None`, return an unbound graph with the
   same topology and open no DB/model/network resource. If execution is
   requested and live mode is disabled/missing token, return the same
   topology but let its live seed emit sanitized `admission_rejected`. For
   enabled execution: validate JWT signature, audience, expiry, session
   revocation, current role, disabled status, and authorization version;
   open one per-run `app_api` DB connection; build process and run-scoped
   deps; create a live seed closure capturing caller/connection, not the
   token; compile and yield the graph; close every resource in `finally`.
4. Modify `build_query_graph` with mutually exclusive `studio_local` and
   `studio_live` modes. Reject both together. Both Studio modes reuse
   `StudioQueryInput`, `StudioQueryState`, and `emit_studio_response`.
   Production mode is unchanged.
5. Use existing core durable admission. For each Studio turn: query text from
   `query_text_from_studio_input`; conversation ID is stable `uuid5` from
   Studio thread ID under `STUDIO_LIVE_NAMESPACE`; reserve the same
   Auto/Composite maximum used by the production app; idempotency key is
   `uuid5(STUDIO_LIVE_NAMESPACE, thread_id + ":" + last_human_message_id_or_turn_index + ":" + payload_hash)`;
   call normal rate/admission/budget logic with the verified caller; return
   the real admitted context whose status must never be `studio_local`.
   Failures return `admission_rejected` plus sanitized detail and one
   assistant message. OpenAI and retrieval must not run. Run the existing
   LangSmith governance gate before company content can be traced/exported.
6. Register separately:

   ```json
   "query_studio_live": "./src/smart_rag_agents/query/studio_live.py:make_graph"
   ```

## Acceptance checks

- Introspection opens zero sockets.
- Disabled live mode rejects and never synthetic-admits.
- Missing/expired/invalid/revoked token rejects before DB/model.
- Valid mocked JWT/profile/admit returns non-`studio_local` context.
- Repeated retry with the same human message reuses the idempotency key.
- Repeated identical new turn gets a different key.
- Role/version change is rechecked.
- Connection closes on success/error/cancel.
- Token/canary does not appear in serialization/log/trace.
- Import-boundary and existing `query_studio` tests stay green.

```powershell
uv run pytest tests/contract/test_langgraph_config.py tests/contract/test_import_boundaries.py tests/unit/test_query_studio.py tests/unit/test_query_studio_live.py tests/unit/test_query_graph_runtime.py -q
uv run ruff check apps/agents/src/smart_rag_agents/query/studio_live.py apps/agents/src/smart_rag_agents/query/live_runtime.py apps/agents/src/smart_rag_agents/query/graph.py packages/core/src/smart_rag_core/security/profile_snapshot.py
uv run pyright apps/agents/src/smart_rag_agents/query/studio_live.py apps/agents/src/smart_rag_agents/query/live_runtime.py apps/agents/src/smart_rag_agents/query/graph.py packages/core/src/smart_rag_core/security/profile_snapshot.py
```

No live success may be claimed until a real JWT, hosted Supabase, budget,
OpenAI, and retrieval boundary are available.

## Negative tests

- Agents importing FastAPI/backend, `AgentSettings` inheriting
  `BackendSettings`, a service-role setting, synthetic admission, token
  leakage, or changing the `query_studio` graph entry fails the packet.

## Stop routes

- Stop if the pinned Agent Server factory signature is unsupported.
- Stop if authorization would require a service-role key or synthetic
  identity.
- Stop if a required live boundary is unavailable and only a fake success
  could pass.

## Required evidence

- Append to
  [`phase-06-agent-intelligence-evidence.md`](../../../../../docs/development/phase-06-agent-intelligence-evidence.md):
  factory-signature source, import-boundary proof, admission/idempotency/
  redaction tests, exact commands/exit codes, unverified live JWT checks,
  rollback (remove `query_studio_live` registration), and P06-14 handoff.
