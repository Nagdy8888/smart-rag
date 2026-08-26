# Candidate Backend Progress Packets

Status: **candidate, non-canonical**

Pinned fact: `apps/agents/pyproject.toml` uses LangGraph 1.2.11. Production
currently requests `stream_mode="updates"` and emits status only after node
updates. There is no custom writer or `tool_progress` event yet.

All BEP packets are blocked until GOV-00 adds the superseding Phase 6/8
amendments, plan integrity passes, and MOD-01 has created the frontend type
owners. They are also blocked until BMOD-01 through BMOD-09 pass; behavior is
never added to the pre-refactor backend god files.

## BEP-01 — Additive SSE progress catalog

**Objective:** define bounded, non-sensitive progress payloads before any
producer emits them.

**Modify**

- `packages/core/src/smart_rag_core/sse/catalog.py`;
- the BMOD-06 owner
  `apps/backend/src/smart_rag_api/services/sse/mapping/contracts.py`;
- after MOD-01, `apps/frontend/src/lib/types/sse.ts`;
- the canonical SSE/OpenAPI documentation named by DOC-01.

**Contract**

```python
class StatusPayload(_SsePayload):
    stage: str
    status: str
    phase: Literal["started", "completed", "failed"] | None = None

class ToolProgressPayload(_SsePayload):
    tool_key: str
    phase: Literal["started", "completed", "failed"]
```

Add `tool_progress` to the event type catalog. Keep `phase` optional so existing
persisted status rows replay. Preserve current field-length limits; cap stage
and tool key at 64 if not already bounded.

Synchronize `phase`, `tool_key`, the public event union, and any generated API
contract in this same packet. A catalog-only change is incomplete.

BEP-01 owns only wire-level frontend names/payload shapes in `types/sse.ts`.
FEP-01 later owns `RunProgressState`, reducer transitions, and UI-facing
progress types; it must not redefine the wire strings.

**Never include:** timestamps invented by the client, display text, prompt,
query, args, result, passage, source, error message, traceback, or token.

**Tests**

- add `tests/unit/test_sse_catalog_progress.py`;
- validate each legal phase and reject every other phase;
- reject extra/forbidden keys;
- validate a legacy status payload without `phase`;
- prove unknown event types still fail.

Do not bump the schema major for an additive event unless the promoted canonical
packet explicitly changes the handshake contract.

```powershell
uv run pytest tests/unit/test_sse_catalog_progress.py tests/unit/test_sse_protocol.py -q
uv run ruff check packages/core/src/smart_rag_core/sse/catalog.py apps/backend/src/smart_rag_api/services/sse/mapping/contracts.py
pnpm --filter smart-rag-frontend lint
```

## BEP-02 — LangGraph v2 stream-part adapter

**Objective:** parse the pinned 1.2.11 multi-mode shape without changing the
production executor yet.

**Add**

- `apps/backend/src/smart_rag_api/services/sse/stream_parts.py`;
- `tests/unit/test_sse_stream_parts.py`;
- `tests/contract/test_langgraph_stream_v2.py`.

**Keep** `sse/chunks.py` as a small compatibility facade.

**Typed adapter**

```python
@dataclass(frozen=True)
class ParsedStreamPart:
    mode: Literal["updates", "custom"]
    namespace: tuple[str, ...]
    data: object

def parse_stream_part(raw_chunk: object) -> ParsedStreamPart | None: ...
def updates_mapping_from_part(
    part: ParsedStreamPart,
) -> dict[str, object] | None: ...
def custom_mapping_from_part(
    part: ParsedStreamPart,
) -> dict[str, object] | None: ...
```

Support:

- v2: `{"type": "custom|updates", "ns": (...), "data": ...}`;
- v1 multi-mode tuples for compatibility;
- current raw mapping as legacy updates-only input.

Unknown modes/shapes return `None`; they are not guessed to be updates.

The contract test must build a tiny real `StateGraph`, call
`get_stream_writer()`, stream with
`stream_mode=["updates", "custom"], version="v2"`, and assert the observed
shape/order on the installed version.

```powershell
uv run pytest tests/unit/test_sse_stream_parts.py tests/contract/test_langgraph_stream_v2.py -q
```

**Stop:** if the pinned runtime shape differs, update this candidate and
canonical contract from observed data before implementation.

## BEP-03 — Truthful node-start emission

**Objective:** emit a node start immediately before substantive node work while
using normal updates as completion proof.

**Prerequisite:** BMOD-01 has reduced `graph.py` and extracted bound-node
construction.

**Add**

- `apps/agents/src/smart_rag_agents/query/streaming/__init__.py`;
- `apps/agents/src/smart_rag_agents/query/streaming/progress.py`;
- `tests/unit/test_query_progress_wrapper.py`.

**Modify:** `apps/agents/src/smart_rag_agents/query/graph.py` wiring only.

**Custom shape**

```python
class NodeStartCustom(TypedDict):
    kind: Literal["node_start"]
    stage: str
```

**Wrapper behavior**

1. receive the compiled graph stage name and existing callable;
2. when the graph actually invokes that callable and it is not a known
   terminal/no-op closed state, call
   `get_stream_writer()({"kind": "node_start", "stage": stage})`;
3. invoke the original callable unchanged;
4. do not emit completed; the resulting `updates` part is completion proof;
5. do not catch/translate node exceptions here.

Apply only to these exact production stage keys registered in
`build_query_graph`:

```text
enforce_admission
load_memory
prepare_query
compile_plan
company_scope
general_scope
mixed_scope
invalid_scope
apply_correction
fuse_evidence
compose_tables
disclose_optional_tools
generate_answer
verify_answer
```

Do not wrap `seed_studio_runtime`, `seed_studio_live_runtime`, or
`emit_studio_response`. Friendly frontend labels map from the exact keys above;
never emit shorthand such as `admission`, `memory`, or `tools`.

**Route truth:** a node omitted by routing emits nothing. A wrapper guard must
avoid starts for a node invoked only to return the existing closed-state no-op.

**Architecture:** `graph.py` remains topology wiring. If wrappers make it grow,
move bound-node construction to the streaming module. No backend SSE imports in
agents.

**Tests**

- start appears before the same node's update;
- skipped route nodes emit zero starts;
- closed-state no-op emits zero starts;
- existing graph node set and route tests remain identical;
- custom payload contains only `kind` and `stage`.

```powershell
uv run pytest tests/unit/test_query_progress_wrapper.py tests/unit/test_scope_graph_routes.py tests/contract/test_langgraph_stream_v2.py -q
```

## BEP-04 — Framework-neutral optional-tool progress

**Objective:** observe only role-filtered selected tool keys without importing
LangGraph into core.

**Add**

- `packages/core/src/smart_rag_core/tools/progress.py`;
- `apps/agents/src/smart_rag_agents/query/streaming/tool_progress.py`;
- `tests/unit/test_optional_tool_progress.py`.

**Modify**

- core optional-tool service/executor after verifying current signatures;
- `apps/agents/src/smart_rag_agents/query/nodes/optional_tools.py`.

**Core protocol**

```python
class ToolProgressReporter(Protocol):
    def selected(self, tool_keys: tuple[str, ...]) -> None: ...
    def phase(
        self,
        tool_key: str,
        phase: Literal["started", "completed", "failed"],
    ) -> None: ...
```

The reporter is optional and defaults to no-op. Selection is reported only
after authorization and policy filtering. Emit `started` immediately before
execution, `completed` on success, and `failed` on the existing safe failure
path. Reporter failures are logged and ignored so observability cannot change
tool outcome.

The agent adapter writes:

```python
{
    "kind": "tool_progress",
    "tool_key": selected_key,
    "phase": "started|completed|failed",
}
```

It must reject/report no key that was not in the selected role-visible tuple.

**Tests**

- intent none and skipped mode produce no phases;
- one selected success produces started then completed;
- safe tool failure produces started then failed;
- callback receives no query/argument/result/exception text;
- core has no `langgraph` import.

```powershell
uv run pytest tests/unit/test_optional_tool_progress.py -q
uv run pytest tests/contract/test_import_boundaries.py -q
```

## BEP-05 — Extend the decomposed SSE mapper

**Prerequisite:** BMOD-06 has already reduced `query_sse_mapping.py` to a
≤100-line compatibility facade with move-only parity tests.

**Objective:** add progress to the focused mapping owners without regrowing the
facade.

**Add**

- `progress.py`: strict custom event decoding/deduplication;
- `diagnostics.py`: catalog-backed non-text diagnostics.

Modify the BMOD-06 `mapper.py` and `status.py` owners. Keep
`query_sse_mapping.py` exports-only and ≤100 lines.

**Mapping rules**

- custom `node_start` →
  `status {stage, status: "running", phase: "started"}`;
- node update → existing bounded status plus
  `phase: "completed"` or `"failed"` based on current reject mapping;
- custom `tool_progress` → same typed public event;
- malformed/extra-key custom payload → drop and structured-log metadata only;
- duplicate open start for the same stage → ignore defensively;
- generated draft remains held;
- verified/refused/partial text is chunked only after `verify_answer` update.

**Terminal behavior:** on cancelled/error/partial, frontend may close any active
visual progress row; the mapper must not fabricate successful completion.

**Tests**

- all existing mapper and verified-final tests remain green;
- add `tests/unit/test_sse_mapping_progress.py`;
- malicious custom payload with `query`, `result`, or `error` emits nothing;
- start precedes completed;
- legacy update-only chunks remain valid;
- no `token_delta` before verify.

```powershell
uv run pytest tests/unit/test_query_sse_mapping.py tests/unit/test_query_sse_verified_final.py tests/unit/test_sse_mapping_progress.py -q
```

## BEP-06 — Production v2 multi-mode dispatch

**Objective:** switch only the LangGraph production executor to the verified v2
adapter.

**Prerequisite:** BMOD-02 through BMOD-05 have made `executors.py` a
compatibility facade and isolated `LangGraphQueryRunExecutor`.

**Add:** `apps/backend/src/smart_rag_api/services/sse/stream_dispatch.py`.

**Modify:** the minimum code in
`apps/backend/src/smart_rag_api/services/sse/langgraph_executor.py`. Do not put
runtime logic back into `executors.py`.

**Required call**

```python
compiled.astream(
    state,
    config,
    stream_mode=["updates", "custom"],
    version="v2",
    context=QueryGraphContext(deps=deps),
)
```

For each raw part:

1. preserve the current database commit before derived event persistence;
2. honor cancellation;
3. parse via `parse_stream_part`;
4. custom → mapper progress method;
5. updates → token accounting plus mapper update method;
6. validate every draft through the central catalog;
7. yield one draft at a time so service append/sequence remains durable;
8. preserve stream close, terminal, settlement, and exception behavior.

**Required ordering**

```text
node status started
optional tool progress events
node status completed/failed
verify completed
verified token_delta events
one terminal
```

Fast nodes may start and complete in adjacent events. No artificial backend
sleep or forced paint is allowed.

**Tests**

- add `tests/unit/test_query_sse_progress_ordering.py`;
- extend lifecycle/settlement/verified-final tests;
- assert commit occurs before processing each stream part;
- cancel after started persists partial timeline and one terminal;
- reconnect replay does not invoke provider again.

```powershell
uv run pytest tests/unit/test_query_sse_progress_ordering.py tests/unit/test_query_sse_lifecycle.py tests/unit/test_query_sse_settlement.py tests/unit/test_query_sse_verified_final.py -q
```

## BEP-07 — Route, replay, and leakage proof

**Objective:** prove real route awareness rather than a hard-coded pipeline.

**Add**

- `tests/unit/test_query_sse_route_progress.py`;
- `tests/contract/test_sse_progress_replay.py`.

Reuse route fixtures from `tests/unit/test_scope_graph_routes.py`.

**Assertions**

- every executed node has one start and at most one terminal status;
- company/general/mixed/invalid fixtures have explicit required and forbidden
  stage sets derived from actual topology;
- optional tools appear only when selected/executed;
- first `token_delta` follows verify completion;
- serialized events exclude the fixture query, secret marker, draft answer,
  evidence text, tool args/results, and exception text;
- sequence IDs are monotonic;
- resume after N returns only later events;
- legacy persisted status without phase replays;
- cancellation/error closes active UI state without fake completed events;
- exactly one protocol terminal persists.

```powershell
uv run pytest tests/unit/test_scope_graph_routes.py tests/unit/test_query_sse_route_progress.py tests/contract/test_sse_progress_replay.py tests/contract/test_sse_resume.py -q
```

**Backend exit gate:** do not start frontend progress packets until BEP-01
through BEP-07 pass and the public SSE fixture is checked in.

**Dependency reminder:** all BMOD-01–BMOD-09 packets precede BEP-01. Within
that completed baseline, BMOD-01 owns the BEP-03 seam, BMOD-06 owns the
BEP-01/BEP-05 seam, and BMOD-02–BMOD-05 own the BEP-06 seam.
