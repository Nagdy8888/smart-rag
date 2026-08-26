---
name: "Frontend overhaul: visible progress, verified answer streaming, and modular architecture"
overview: "Reviewed, non-canonical remediation proposal for the existing Next.js frontend: keep users informed with persisted node/tool progress while work runs, progressively reveal verified answer text after verification, close the blocked live Phase 8 gate, and refactor oversized frontend/backend files into behavior-preserving focused modules before adding new feature logic."
status: draft-non-canonical
canonical_owner: ".cursor/plans/hybrid-graph-rag/08-phase-frontend-integration.md"
implementation_detail_root: ".cursor/plans/frontend-overhaul-streaming-and-performance_9b680637"
todos:
  - id: governance-baseline
    content: Reconcile canonical Phase 8 status, record a baseline commit and metrics, and promote exactly one accepted scope into one additive packet
    status: pending
  - id: unblock-p08-22
    content: Close live Verifying, settlement, terminal synchronization, and hosted-schema blockers before broad frontend work
    status: pending
  - id: modular-chat-seams
    content: Extract chat-run, progress, SSE, API, and type ownership seams before adding new behavior to ChatApp, api.ts, or types.ts
    status: pending
  - id: modular-backend-stream-seams
    content: Split graph.py, executors.py, executor_support.py, service.py, service_persist.py, and query_sse_mapping.py into bounded topology, runtime, lifecycle, persistence, replay/cancel, and mapping owners before adding custom progress
    status: pending
  - id: security-correctness
    content: Fix the callback open redirect, stale resume/recovery/switch races, session-scoped message caching, and silent destructive/pagination failures
    status: pending
  - id: truthful-progress
    content: Persist and render route-executed node starts/completions plus safe tool selection/execution progress while verified answer text remains private
    status: pending
  - id: verified-answer-reveal
    content: Progressively reveal the verified answer through an isolated adaptive presentation buffer with skip, reduced-motion, accessibility, and maximum-delay guarantees
    status: pending
  - id: diagnostic-events
    content: Add typed optional-tool, applied-correction, Hybrid-coverage, and deadline mappings; defer cache until retrieval exposes an authoritative source
    status: pending
  - id: measured-performance
    content: Baseline and reduce SSE publications, hot-path renders, duplicate readiness calls, blocking fetches, and bundle/module costs without delaying answers
    status: pending
  - id: scroll-ux-a11y
    content: Add pinned autoscroll and prepend anchoring, truthful loading/error/empty states, and complete modal/menu keyboard behavior
    status: pending
  - id: contract-surfacing
    content: Type and render only public citation, ingestion, and deadline fields whose backend/OpenAPI semantics are verified
    status: pending
  - id: god-file-exit
    content: Finish reducing api.ts, types.ts, ChatApp, auth screens, and large feature components to enforced single-responsibility module budgets
    status: pending
  - id: deterministic-verification
    content: Run focused and full lint, type, unit, contract, build, accessibility, visual, and deterministic Playwright gates
    status: pending
  - id: live-verification
    content: Repeat the hosted production-like run and prove truthful progress, verified output, one terminal, settlement, resume, and current schema
    status: pending
isProject: false
---

# Frontend Overhaul: Visible Progress, Verified Answers, and Modular Architecture

## Status and authority

This file is a **reviewed draft and audit handoff**, not an implementation authority. The canonical source remains [Phase 8: Frontend integration](./hybrid-graph-rag/08-phase-frontend-integration.md), its shared contracts, and exactly one selected unchecked packet.

Before application code changes:

1. Reconcile the unchecked P08-07 wrapper item with its completed evidence.
2. Treat the recorded P08-22 live failures as blockers, not polish work.
3. Promote exactly one accepted concern into one additive canonical packet with plan-integrity validation, allowed/forbidden outputs, stop routes, rollback, and evidence requirements.
4. Execute one packet per model run.

This draft does not authorize pre-verification answer text. On August 26, 2026, the user explicitly selected **progress-only before verification** and then approved a **paced verified-answer reveal after verification** so text does not appear in bulk. Canonical promotion must add an ADR superseding the previous no-artificial-delay presentation rule. A future pre-verification reversal requires another explicit decision.

## Primary implementation deliverables — streaming and god-file refactoring

These are the two central implementation tracks. They are not optional polish.

### Track 1 — Visible streaming while the user waits

This design deliberately has two kinds of streaming:

1. **Before verification:** stream truthful server-originated node/tool progress,
   never draft answer prose.
2. **After verification:** append verified `token_delta` events immediately to
   authoritative state, then visibly reveal the verified text over animation
   frames so it does not appear as one bulk block.

Implementation path:

- `BEP-01` adds `status.phase` and `tool_progress` to the public SSE catalog.
- `BEP-02` proves LangGraph 1.2.11 `["updates", "custom"]` v2 output.
- `BEP-03` and `BEP-04` emit actual node starts and authorized tool lifecycle
  events.
- `BEP-05` and `BEP-06` map, persist, sequence, and replay those events without
  releasing draft text.
- `FEP-01` and `FEP-02` reduce the events into a route-aware visible timeline.
- `FEP-03` and `FEP-04` implement the Unicode-safe, ≤2.5-second,
  ≤90-publication verified-text reveal with `Show full answer` and
  reduced-motion bypass.
- `FEP-05` keeps the conversation pinned only while the user remains at the
  bottom.
- `PER-01` coalesces transport publications without dropping progress history
  or the resume cursor.

Streaming is complete only when tests prove:

- progress is visible before answer text;
- skipped nodes/tools never appear;
- `Verifying` comes from the real `verify_answer` node;
- no `token_delta` is accepted before verification;
- a long verified answer has a strict intermediate visible prefix and reaches
  full text within 2.5 seconds;
- reconnect/cancel/replay preserve ordering and never duplicate paid work.

### Track 2 — Refactor every god file before adding ownership

The streaming implementation is forbidden from adding logic to current god
files. Move-only characterization packets run first.

**Refactoring means decomposition, not deletion:** preserve every supported
feature, route, public export, security boundary, and test contract; move
responsibilities into focused modules; retain the original public files as thin
compatibility barrels/facades.

Core stream-path reductions (physical lines, counted with
`Path.read_text().splitlines()`):

```text
apps/frontend/src/components/chat/chat-app.tsx
  1201 -> <=300 physical lines, composition only
apps/frontend/src/lib/api.ts
  2350 -> <=100 physical lines, exports only
apps/frontend/src/lib/types.ts
  685 -> <=100 physical lines, exports only
apps/agents/src/smart_rag_agents/query/graph.py
  476 -> <=300 physical lines, topology only
apps/backend/src/smart_rag_api/services/sse/executors.py
  527 -> <=100 physical lines, compatibility exports only
apps/backend/src/smart_rag_api/services/sse/executor_support.py
  321 -> <=100 physical lines, retained compatibility exports
apps/backend/src/smart_rag_api/services/sse/service.py
  492 -> <=300 physical lines, public attach/orchestration only
apps/backend/src/smart_rag_api/services/sse/service_persist.py
  358 -> <=100 physical lines, compatibility composition only
apps/backend/src/smart_rag_api/services/query_sse_mapping.py
  363 -> <=100 physical lines, compatibility exports only
```

Refactoring path:

- `MOD-01` through `MOD-06` split frontend types, API transport/domains,
  `CitationDrawer`, query ownership, and the single chat-run controller.
- `BMOD-01` through `BMOD-09` split bound graph nodes, executor
  protocol/runtime/lifecycle/persistence, stream service append/replay/cancel,
  and the existing SSE mapper, then enforce physical-line budgets before
  progress behavior is added.
- `MOD-07` through `MOD-19` remove the remaining table, document, admin, auth,
  graph, request-builder, and CSS god files.
- Architecture tests enforce line budgets, barrel-only files, import
  boundaries, and exactly one SSE consumer/reducer/run owner.

No packet may finish with “refactor later.” Every touched god file must become
smaller, and final verification permits no undocumented production source over
the declared budgets.

## Cheap-LLM implementation packet suite

The detailed execution suite is split so a low-cost model receives bounded instructions instead of this entire audit:

- [mandatory execution contract](./frontend-overhaul-streaming-and-performance_9b680637/00-cheap-llm-execution-contract.md);
- [governance, security, and correctness packets](./frontend-overhaul-streaming-and-performance_9b680637/01-governance-security-correctness-packets.md);
- [behavior-preserving modularization packets](./frontend-overhaul-streaming-and-performance_9b680637/02-modularization-packets.md);
- [backend streaming modularization packets](./frontend-overhaul-streaming-and-performance_9b680637/02b-backend-modularization-packets.md);
- [backend node/tool progress packets](./frontend-overhaul-streaming-and-performance_9b680637/03-backend-progress-packets.md);
- [frontend progress and verified-reveal packets](./frontend-overhaul-streaming-and-performance_9b680637/04-frontend-progress-reveal-packets.md);
- [performance, UX, and accessibility packets](./frontend-overhaul-streaming-and-performance_9b680637/05-performance-ux-accessibility-packets.md);
- [contract, documentation, deterministic, and hosted verification packets](./frontend-overhaul-streaming-and-performance_9b680637/06-contract-docs-verification-packets.md);
- [P08-22 blocker diagnosis and repair packets](./frontend-overhaul-streaming-and-performance_9b680637/07-p08-22-blocker-packets.md);
- [remaining frontend god-file refactoring packets](./frontend-overhaul-streaming-and-performance_9b680637/08-remaining-modularization-packets.md).

Give the implementation model the execution contract plus **one promoted packet ID only**. Require it to quote objective, paths, forbidden changes, stop conditions, and acceptance checks before editing. It must stop after that packet, even when a sibling looks easy. These linked files are still candidate detail, not canonical authority.

## Review corrections applied

The earlier version contained useful audit findings but was unsafe to execute. This revision:

- removes deceptive pre-verification/typewriter claims and records the later user-approved, verified-only paced reveal as an explicit presentation policy;
- replaces invented active-node timing with server-originated, replay-safe start/completion phases and no elapsed-time claim;
- makes the timeline route-aware, so skipped nodes never appear;
- corrects diagnostic event field sources and defers `cache`;
- retains the 4096-character answer limit until persistence/replay benchmarks justify a change;
- makes P08-22 release blockers explicit prerequisites;
- separates client convenience validation from authoritative server security;
- treats `citation_preview.ranks` as ordinals, not retrieval relevance;
- replaces blanket API timeouts with operation-specific finite-request deadlines;
- records that session restore already renders a workspace skeleton;
- records that pinned `@supabase/ssr` browser clients are singleton by default, so factory consolidation is dependency cleanup rather than a performance fix.

## User-approved product priorities

The implementation must optimize for these priorities in order:

1. **No blind waiting:** the active node and authorized tool activity remain visible throughout a run.
2. **Truthful progress:** show only work the server actually started/completed; never predict skipped nodes or invent elapsed time.
3. **Verified answer streaming:** no draft prose appears before verification. After verification, verified text is progressively revealed from a client presentation buffer so it does not appear in bulk.
4. **No god files:** new progress/streaming behavior is built in focused modules. `chat-app.tsx`, `api.ts`, and `types.ts` become thin composition/barrel files rather than receiving more logic.

## Historical frontend audit baseline

One August 26, 2026 ad-hoc review of the dirty workspace produced this historical snapshot:

- strict TypeScript passed;
- all 47 Vitest files and 327 tests passed;
- the Next.js production build passed;
- ESLint failed at `chat-app.tsx:372` because the `/me` error effect synchronously calls `setFailure`;
- Playwright reported 30 passed, 5 skipped, and 1 failed;
- authenticated browser runs repeatedly logged a real AppShell hydration mismatch between server and `localStorage` navigation state;
- the 390px Documents capture squeezed `Checking` into a vertical character column and collided with brand/title chrome;
- the visual failure compared a still-loading Documents page with an empty-state baseline because capture waits only for `#main`, not a deterministic data state.

These counts are not reusable proof and differ from earlier canonical evidence runs. Re-run the same gates after isolating the accepted packet and record the commit, environment, fixtures, actual counts, and skip count.

## Non-negotiable streaming decision

The selected policy is **progress-only before verification**:

- `generate_answer`, `general_scope`, and `mixed_scope` drafts stay private until deterministic verification finishes.
- During retrieval, tool execution, generation, and verification, the UI streams persisted node/tool progress only.
- Persisted `token_delta` compatibility events carry only verified/refused/partial prose.
- The reducer appends every verified chunk immediately to the authoritative in-memory answer; a separate presentation buffer reveals that verified text progressively.
- The UI labels the transition truthfully as `Verified — displaying answer`; it never implies the model is still generating.
- The reveal begins on the next animation frame, spans at least two paints for answers longer than 80 grapheme clusters, and completes within 2.5 seconds of verified-text availability.
- Adaptive grapheme batches use at most 90 reveal-owned React publications per answer. Backlog catch-up satisfies the 2.5-second ceiling.
- `Show full answer` immediately completes the reveal. `prefers-reduced-motion: reduce` bypasses pacing and shows the full verified answer at once.
- Historical/reloaded messages never replay the animation. Conversation switch, a new send, or user selection/copy intent completes the current reveal immediately; unmount cancels scheduled work.
- Protocol terminal, persistence, usage settlement, resume cursor, and citation availability do not wait for presentation. The timeline remains visible until reveal completion, then collapses to an expandable summary.
- Screen readers receive one polite `Verified answer ready` announcement, not per-slice announcements.
- Backend chunk size remains an event-budget decision, not an animation mechanism.
- Metrics use **verified answer availability**, not provider time-to-first-token.

## Gate 0 — Close the existing P08-22 blockers

The current evidence still records:

- live `Verifying` was not captured;
- durable usage settlement rows remained absent;
- the UI could remain `running` after a durable `partial`;
- the hosted schema lagged repository migrations.

Split Gate 0 into the explicit `P08B-*` packets. Diagnose first, then close hosted schema parity, durable settlement, and durable-terminal/UI synchronization before broad frontend work. The missing live `Verifying` proof is closed by the canonically amended `BEP-*` progress path and repeated `P08B-05` proof; do not fake it with a timer while custom progress is still unimplemented. Node progress has no minimum duration, fake timer, or forced paint; the separately approved answer reveal begins only after verification.

After repair, repeat one bounded provider run and prove hosted durability, one terminal, settlement, and local-fixture absence.

## Target architecture

```mermaid
flowchart LR
    graph["LangGraph route-specific execution"] --> custom["Custom node/tool start progress"]
    graph --> updates["Completed node updates"]
    custom --> events["Persisted monotonic progress events"]
    updates --> events
    events --> timeline["Active + completed node/tool timeline"]
    graph --> verify["Deterministic verification"]
    verify --> chunks["Verified token_delta chunks"]
    chunks --> buffer["Authoritative verified-text buffer"]
    buffer --> reveal["Bounded paced visual reveal"]
    graph --> diagnostics["Typed diagnostics with authoritative sources"]
    diagnostics --> details["Collapsed run details"]
```

## Architecture rule — refactor god files without removing behavior

Modularization is not postponed to the end. Use a strangler workflow inside each accepted packet:

1. add characterization tests around the behavior being moved;
2. extract the smallest ownership seam without changing behavior;
3. implement the new behavior in that seam;
4. prove parity and leave every touched god file smaller.

The first chat packet establishes these boundaries:

- `apps/frontend/src/lib/api.ts` becomes a compatibility barrel; request primitives live under `apps/frontend/src/lib/api/{errors,http,headers,parsers}.ts`, chat requests in `apps/frontend/src/lib/api/chat.ts`, and event-stream transport in `apps/frontend/src/lib/api/sse.ts`;
- `apps/frontend/src/lib/types.ts` becomes a compatibility barrel over domain files such as `apps/frontend/src/lib/types/chat.ts` and `apps/frontend/src/lib/types/sse.ts`;
- `apps/frontend/src/components/chat/chat-app.tsx` becomes composition only;
- run lifecycle moves to `apps/frontend/src/components/chat/hooks/use-chat-run.ts`;
- query ownership moves to `apps/frontend/src/components/chat/hooks/use-chat-queries.ts`;
- replay-safe progress reduction moves to `apps/frontend/src/lib/run-progress.ts`;
- the existing `apps/frontend/src/components/chat/run-progress.tsx` status helper remains during migration, while timeline rendering moves to `apps/frontend/src/components/chat/run-progress-timeline.tsx`;
- verified-text presentation state moves to `apps/frontend/src/components/chat/hooks/use-verified-answer-reveal.ts`;
- paced rendering moves to `apps/frontend/src/components/chat/verified-answer-reveal.tsx`;
- backend LangGraph custom progress adaptation lives under `apps/agents/src/smart_rag_agents/query/streaming/`, and public SSE progress mapping lives under `apps/backend/src/smart_rag_api/services/sse/mapping/`; neither expands `graph.py`, `executors.py`, or `query_sse_mapping.py` into a new god file.

Exit budgets:

- `chat-app.tsx` is at most 300 physical lines and contains no fetch/SSE parsing;
- `api.ts` and `types.ts` are each at most 100 physical lines and contain exports only;
- `graph.py` is at most 300 physical lines and owns topology only;
- `executors.py`, `executor_support.py`, `service_persist.py`, and
  `query_sse_mapping.py` are each at most 100 physical lines as compatibility
  facades/exports retained after migration;
- `service.py` is at most 300 physical lines and owns public attach/orchestration only;
- each new production module is at most 300 physical lines and owns one concern;
- the final MOD-19 gate leaves no non-generated production TypeScript/TSX or concern-owned CSS module over 300 physical lines without an explicit reviewed data-only exception;
- tests are split by owner; no replacement god test file;
- import-cycle and prohibited-cross-domain checks pass.

Line limits are guardrails, not permission to hide complexity in dense code. Cohesion, typed contracts, and test ownership remain mandatory.

## Packet A — Security and correctness

### Open redirect

Fix `safeNextPath` in [`auth/callback/route.ts`](../../apps/frontend/src/app/(auth)/auth/callback/route.ts):

- reject backslashes and malformed/encoded network-path variants;
- parse against the request origin and require the resulting origin to remain identical;
- allow only application-relative paths;
- test `//evil.example`, `/\evil.example`, `/\\evil.example`, encoded slash/backslash variants, absolute URLs, and valid relative paths.

### Chat and cache races

After extracting `use-chat-run.ts`, repair the lifecycle there; [`chat-app.tsx`](../../apps/frontend/src/components/chat/chat-app.tsx) only wires the hook:

- resume stream errors from the latest `current`/ref state, never the render closure;
- classify every non-OK resume GET before passing its body to the SSE parser; stop reconnect for revoked/forbidden/server failures and preserve the special deleted-run route;
- abort the recovery controller during effect cleanup;
- use abort plus latest-wins tokens for conversation selection and load-earlier;
- prevent old responses from mutating a newly selected conversation;
- session-scope the conversation-message query key and clear caller-specific pages when the JWT `sub` changes, not only when the token becomes `null`;
- add a catch and visible retry for load-earlier;
- require confirmation and visible failure handling for conversation deletion;
- remove the current lint-blocking state mirror: derive the `/me` classified failure or update it from an asynchronous query boundary instead of synchronously calling `setFailure` in an effect.

### Boundary language

- Client file size/type and crawl URL checks are early feedback only. The server remains authoritative for quota, media validation, SSRF policy, authorization, quarantine, scanning, and parser limits.
- `CitationChip` may defensively reject unsafe URLs, but production citation links remain disabled until an authorized source-opening contract exists.
- In `SEC-03`, add `poweredByHeader: false`. Define and verify HSTS at the actual HTTPS edge owner before enabling preload or subdomain policy.

## Packet B — Live node/tool progress and verified answer streaming

### Public progress contract

The pinned LangGraph `1.2.11` supports unified multi-mode streaming. The executor uses:

```python
compiled.astream(
    state,
    config,
    stream_mode=["updates", "custom"],
    version="v2",
    context=query_context,
)
```

Per the current LangGraph [v2 stream format](https://docs.langchain.com/oss/python/langgraph/streaming#stream-output-format-v2) and [custom data contract](https://docs.langchain.com/oss/python/langgraph/streaming#custom-data), data emitted with `get_stream_writer()` arrives as typed `StreamPart` records, while `updates` continues to carry completed node state. Add a contract test against the pinned version before production wiring.

Public SSE behavior:

- extend `status` additively with `phase: "started" | "completed" | "failed"`;
- emit `status(stage=<executed node>, status="running", phase="started")` from a dedicated node wrapper immediately before work;
- map the corresponding `updates` record to `phase="completed"` while preserving its bounded outcome status;
- add `tool_progress` with safe `tool_key` and `phase: "started" | "completed" | "failed"`;
- update the shared extra-forbid SSE catalog, frontend known-event union, reducer, public docs, and contract fixtures together; keep `status.phase` optional for old persisted rows;
- retain `optional_tool_disclosure` as the authorized selection summary;
- persist every event through the existing sequenced event store so reconnect/replay reconstructs the same timeline;
- emit no prompt, arguments, query, result, passage, snippet, exception, or trace text.

The optional-tool service receives a framework-neutral typed progress callback after authorization/selection and immediately around execution. The core package does not import LangGraph.

### Frontend progress model

`lib/run-progress.ts` owns the pure replay-safe reducer:

```typescript
type RunProgressItem = {
  id: string;
  kind: "node" | "tool";
  key: string;
  phase: "started" | "completed" | "failed";
  outcome: string | null;
  firstSequence: number;
  lastSequence: number;
};
```

Do not add a client-receipt timestamp: replay would timestamp old events as new. Show a spinner only for a received `started` item without a later terminal phase. Do not show elapsed time until a server timestamp contract exists.

Render only stages that actually arrived:

- company routes may execute correction, fusion, tables, tools, answer, and verify;
- general/user-text and mixed clarification routes skip most company nodes;
- invalid/admission/routing exits terminate early;
- friendly labels lead; technical node/tool keys remain available in collapsed details;
- tool selection is visible before execution, then each used tool shows started/completed/failed;
- unknown stages render as safe neutral technical text;
- no route fixture may show phantom steps.

While progress streams, `answerText` remains empty. After `verify_answer` completes, verified `token_delta` events append immediately to authoritative state and feed `VerifiedAnswerReveal`; the visual timeline collapses only after reveal completion.

### Verified answer reveal

`use-verified-answer-reveal.ts` is presentation-only:

- input is verified text plus a presentation key identifying a run created live in this mounted session; protocol terminal does not disable an in-progress reveal;
- output is `visibleText`, `isRevealing`, and `showFullAnswer`;
- segmentation uses `Intl.Segmenter` when available and otherwise reveals the full string rather than risk unsafe slicing; it never corrupts Arabic, emoji, combining marks, citations, or bidirectional text;
- scheduling uses `requestAnimationFrame` with adaptive batches, a 2.5-second hard ceiling, and at most 90 state publications;
- cleanup cancels the scheduled frame and exposes the full verified text;
- reduced motion, historical messages, reload/replay, conversation changes, new sends, and the skip action bypass the remaining animation;
- no presentation offset is persisted or included in the SSE resume cursor;
- pinned autoscroll follows reveal only while the user remains at the bottom.

`VerifiedAnswerReveal` owns no network, query, persistence, terminal, citation, or protocol state. `AnswerSurface` composes it without absorbing its scheduling logic.

### Target mapper additions (not implemented in the current mapper)

After BEP-05 decomposes [`query_sse_mapping.py`](../../apps/backend/src/smart_rag_api/services/query_sse_mapping.py), add:

- `optional_tool_disclosure`: map `optional_selected_keys` to `tool_keys`;
- `tool_progress`: accept only role-filtered selected keys and lifecycle phases from the dedicated progress adapter;
- `route_correction`: emit only when `correction.applied` is true; map explicit from/to routes and the typed reason;
- `coverage`: read the Hybrid `branch_results[].coverage_score`, not `FusionResult`, and add `coverage_score` to mapper allow-fields;
- `deadline`: replace the current `route_family: null` behavior with the authoritative executor/mapper route family before frontend rendering;
- `cache`: **defer** until retrieval propagates a typed safe cache result into graph state.

For every route, assert exactly one started event and at most one completed/failed event per executed node. Skipped topology nodes emit nothing.

### Answer event budget

Keep the current 4096-character default. Every persisted answer event can incur a database append transaction, so a 256-character default can multiply writes and replay rows without improving pre-verification latency. The client reveal buffer creates the requested visual progression independently of durable event granularity.

Change the default only if a dedicated benchmark proves:

- bounded events per representative answer;
- acceptable append and terminal latency;
- acceptable replay cost after disconnect;
- identical reconstructed text and first-terminal behavior.

## Packet C — Measured performance

Capture a baseline before edits:

- readiness request count per 15-second interval;
- `onState` publications per `reader.read()` batch;
- ChatApp, ChatComposer, history, and live-answer React commits;
- shell paint and verified-answer-availability timings;
- persisted events and replay duration for representative answers;
- production build/bundle output.

Then:

- coalesce one React publication per parsed read batch while preserving internal `lastSequence`, first-terminal-wins, run ownership, and resume;
- avoid a React publication for heartbeat-only batches while retaining sequence/pointer bookkeeping;
- stabilize `onLoadEarlier`, `send`, and `reconnect` without stale state;
- use one role-aware readiness query and one 15-second poll;
- parallelize public/operator readiness only when authorization permits the operator probe;
- use per-resource `staleTime`; do not impose one global value on authorization- or freshness-sensitive queries;
- make AppShell's server and first client render deterministic; read the stored navigation preference through a hydration-safe external-store/cookie contract so descendants do not change icon, label, and `aria-expanded` during hydration;
- apply operation-specific timeouts to finite requests and compose them with caller cancellation;
- do not apply a short generic timeout to long-lived SSE;
- verify exact proxy route/cookie-refresh behavior before narrowing `getClaims`;
- lazy-mount closed run details and remove historical-message live regions.

Use the pre-established `use-chat-run`, SSE transport, and progress reducer boundaries. Do not reintroduce stream ownership into ChatApp.

## Packet D — Scroll, states, and accessibility

### Conversation scrolling

- Own scroll behavior at the actual conversation scroll container.
- Follow the bottom while pinned.
- Release pinning when the user intentionally scrolls up.
- Provide “Jump to latest” to restore pinning.
- Preserve the visible anchor when older messages are prepended.
- Test resize, long answers, terminal insertion, reconnect, and reduced motion.

### Truthful query states

Conversations, documents, tables, and tools must render distinct pending, error, and genuinely empty states. Errors never reuse empty copy. In particular, Tables must not render “No structured tables” while its first query is pending.

### Modal and keyboard behavior

- Prefer the existing modal `Sheet` behavior or bring `Drawer` to equivalent backdrop, scroll-lock, focus-trap, Escape, and focus-restore semantics.
- Add CommandMenu Tab trapping, scroll lock, and trigger restoration.
- Move focus into `Menu` when opened and support Home/End.
- Do not nest a Delete button inside a `role="option"` conversation row; use one listbox tab stop or change the collection to a semantic list with separately operable actions.
- Keep the graph List view as a keyboard-operable equivalent and make the Canvas selection path discoverable without pointer-only node clicks.
- Do not move focus after Send without a tested screen-reader/keyboard decision; a polite live region may be less disruptive.
- Scope polite announcements to current progress/final availability, not every persisted history row.

### Responsive shell and visual stability

- At 390px, reserve explicit width for menu/title/account and prevent readiness text from shrinking one character per line; hide the duplicate mobile brand or collapse readiness to an accessible compact indicator.
- Test every product route at 390px and 200% zoom, not only Auth/Ask.
- Visual snapshots must wait for a named deterministic loading or settled state before capture. Never update the baseline merely to accept the current header collision.

## Packet E — Typed contract surfacing

- Define public citation provenance fields in backend schema/OpenAPI before frontend types. Never infer field stability from an open `Record<string, unknown>`.
- Treat `citation_preview.ranks` as display ordinals (`1..N`), not `hybrid_rank`, `graph_rank`, or `combined_score`.
- Render retrieval/fusion scores only when the public citation API defines and returns those exact semantics.
- Add ingestion fields already present in the backend response (`chunk_count`, `embedding`, `queue_age`, `version_number`, `title`) to the frontend decoder/types and technical details.
- Parse deadline route family only after the backend stops emitting `null`.
- Standardize backend auth error details to typed snake-case codes; `session_revoked` currently drifts from the frontend's expected value.
- Remove dead `completed.refusal` parsing only with compatibility tests and documentation.

All OpenAPI/SSE changes remain additive within the major version.

## Packet F — God-file completion gate

This is a **checklist-only gate, not a runnable mega-packet**. Execute the named
`MOD-*` packets one at a time. Work starts after the isolated open-redirect
hotfix and Gate 0 blocker repair, then closes here after behavior/contracts
stabilize:

- MOD-01 through MOD-03 split types/API and keep thin compatibility barrels;
- MOD-04 through MOD-06 retain exactly one `use-chat-run` engine and one
  `use-chat-queries` layer, and move the existing inline `CitationDrawer`;
- BMOD-01 through BMOD-09 split graph node bindings, executor
  runtime/lifecycle/persistence, stream attach/append/replay/cancel, and the
  pre-progress SSE mapper, then enforce those budgets;
- MOD-07 through MOD-10 split table, document, and curation owners;
- MOD-11 splits `auth-screens.tsx` per screen;
- MOD-12 through MOD-15 and MOD-19 split concern-owned CSS and admin builders;
- MOD-16 and MOD-17 split graph/document-detail/import owners;
- MOD-18 creates shared `useApiAuth`, `useCurrentUser`, and
  `newIdempotencyKey` owners after characterization;
- every MOD packet splits tests beside the owning domain.

Each packet separates characterization/extraction proof from behavior assertions. Final acceptance enforces the architecture budgets above; “follow-up refactor” is not an accepted exit.

## Verification and evidence

Each promoted packet adds focused positive, failure, authorization, idempotency, fallback, and replay tests as applicable.

Required deterministic coverage:

- reducer tests for node/tool started/completed/failed, applied/skipped correction, coverage, deadline, unknown events, duplicate sequence, replay, and first terminal;
- pinned LangGraph multi-mode contract tests for `updates` plus `custom` v2 output;
- mapper tests for each feasible diagnostic and rejection of forbidden fields/source text;
- stale-resume, recovery abort, latest-wins selection/load-earlier, and cross-user message-cache tests;
- open-redirect adversarial matrix;
- autoscroll pin/release and prepend-anchor tests;
- loading/error/empty and modal keyboard tests;
- no nested interactive control in the session listbox, plus keyboard-equivalent graph selection;
- the numeric `PER-03` render/publication/readiness ceilings and their focused assertions;
- zero AppShell hydration errors and stable 390px/200%-zoom product-route captures;
- deterministic Playwright SSE fixtures proving progress appears before answer text, skipped nodes never appear, tool phases replay correctly, no token delta appears before verification, verified chunks append immediately afterward, and reconnect/cancel/terminal remain correct;
- fake-clock/component tests for grapheme-safe progressive reveal, at least two paints over 80 graphemes, 2.5-second/90-publication ceilings, adaptive catch-up, skip, reduced motion, cleanup, autoscroll release, and one screen-reader announcement;
- deterministic fake-clock/component proof of intermediate reveal paints plus browser proof of integrated waiting/revealing/complete states; screenshots are not used as a timing oracle;
- a required authenticated-browser job that reports and fails on unexpected skips instead of silently passing without live coverage.
- architecture checks for line budgets, barrel-only files, import cycles, and prohibited SSE/fetch ownership in ChatApp.

Required commands, discovered from the repository:

- frontend lint, strict typecheck, Vitest, production build, and full Playwright;
- targeted backend mapper/unit/contract tests;
- documentation links/Mermaid checks;
- plan-integrity validation for each canonical packet.

Final live closure repeats P08-22 against the hosted runtime and proves:

- truthful node/tool progress throughout the wait without provisional prose;
- a visibly progressive, skippable verified-answer reveal that completes within 2.5 seconds and is bypassed for reduced motion;
- non-empty verified answer or grounded refusal;
- exactly one terminal;
- durable settlement and assistant message;
- monotonic resume with no duplicate provider cost;
- current hosted migrations;
- matching run IDs absent from the local Supabase fixture.

## Execution order

1. `GOV-00`: canonical amendment, required ADRs, integrity, and fresh baseline.
2. `SEC-01`: isolated same-origin callback redirect hotfix—the first application-code change.
3. `P08B-00`: reproduce and classify the hosted failures without code changes.
4. `BMOD-01` through `BMOD-09`: decompose the backend graph, executor, stream service, persistence, and mapper god files; enforce physical-line budgets.
5. `P08B-01` through `P08B-03`: repair hosted schema parity, settlement, and terminal synchronization, then run a bounded hosted checkpoint.
6. `SEC-02`, then `MOD-01` through `MOD-06`: align revoked-session behavior and establish enforced type/API/chat ownership seams.
7. `COR-03` and `COR-04`: repair subject cache isolation and reconnect in the extracted owners.
8. `BEP-01` through `BEP-07`: add the catalog, pinned stream adapter, truthful node/tool producers, multi-mode dispatch, and route/replay/leakage proof to the extracted owners.
9. `FEP-01` through `FEP-05`: replay-safe progress state/UI, Unicode-safe verified reveal, integration, and scroll pinning.
10. `MOD-07` through `MOD-19` in their declared dependency order, plus `PER-01` through `PER-03` and `UX-01` through `UX-06`: refactor remaining oversized files without removing behavior, measure publication/readiness work, and finish state/accessibility/visual repairs.
11. `CTR-01`, `SEC-03`, and `DOC-01`: surface only authoritative diagnostics, assign edge-header ownership, and synchronize public contracts.
12. `VER-01`: full deterministic gates. `P08B-04` then `P08B-05`/`VER-02`: prove real Verifying progress and repeat hosted production-like closure with no unexpected skips.

The open redirect remains the first new application-code remediation. Progress work never adds logic to the existing god files, and no packet exits with a promise to split them later.
