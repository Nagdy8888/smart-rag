# Candidate Modularization Packets

Status: **candidate, non-canonical**

These are behavior-preserving strangler packets. Run existing characterization
tests after every move. Do not add progress or reveal behavior until MOD-06
passes.

## MOD-01 — Split frontend domain types

**Objective:** turn `apps/frontend/src/lib/types.ts` (685 lines) into a
≤100-line compatibility barrel without renaming exports.

**Add under `apps/frontend/src/lib/types/`**

- `auth.ts`: invitation/current-user role contracts;
- `readiness.ts`: meta/dependency/readiness contracts;
- `chat.ts`: conversation, message, run, feedback, citation contracts;
- `documents.ts`: document/upload/crawl/ingestion contracts;
- `graph.ts`: graph search/inspect contracts;
- `tables.ts`: table plan/manifests/results;
- `usage.ts`: usage response;
- `admin-tools.ts`: tool registry/permission contracts;
- `admin-knowledge.ts`: glossary/entity-rule contracts;
- `sse.ts`: answer origins, known/terminal event constants.

**Steps**

1. Inventory every current export from `types.ts`.
2. Move blocks verbatim with their constants; do not alter wire names.
3. Ensure domain files do not import the compatibility barrel.
4. Replace `types.ts` with explicit `export * from "./types/<domain>"`.
5. Keep existing external imports valid.
6. Add a test that compares the expected known event list, not snapshots of the
   source layout.

**Budgets:** barrel ≤100; each domain module ≤220; no circular imports.

**Commands**

```powershell
pnpm --filter smart-rag-frontend typecheck
pnpm --filter smart-rag-frontend exec vitest run src/lib/api.test.ts src/lib/sse.test.ts
```

**Forbidden:** changing event strings, request fields, optionality, or public
names during the move.

## MOD-02 — Split API transport primitives

**Objective:** extract reusable HTTP mechanics from
`apps/frontend/src/lib/api.ts` without changing any request.

**Add under `apps/frontend/src/lib/api/`**

- `errors.ts`: failure unions, `ClassifiedApiError`, sanitization/classification;
- `http.ts`: `apiUrl`, bounded JSON reading, `throwIfNotOk`;
- `headers.ts`: paid, resume, admin mutation headers;
- `parsers.ts`: shared run/feedback response parsers.

**Dependency direction**

```text
types/* <- api/errors <- api/http <- domain API modules
                       <- api/headers
                       <- api/parsers
```

**Steps**

1. Move current code verbatim, including constants and error precedence.
2. Keep `ApiAuth` in one primitive owner.
3. Replace internal references with relative owner imports.
4. Re-export all moved symbols from `api.ts`.
5. Verify no domain module imports `api.ts`; it must import owner modules.

**Budgets:** each module ≤280; no fetch URL/header/status change.

**Tests**

- `api.test.ts` passes before and after;
- safe-detail and rate/retry tests retain exact behavior;
- prohibited-pattern tests are updated only for new owner paths.

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/lib/api.test.ts src/lib/prohibited-patterns.test.ts
pnpm --filter smart-rag-frontend typecheck
```

## MOD-03 — Split API domain modules

**Objective:** make `api.ts` an exports-only barrel ≤100 lines.

**Add under `apps/frontend/src/lib/api/`**

- `readiness.ts`: ready/operator-ready/meta/me;
- `chat.ts`: conversation/history/run/citation/feedback/cancel;
- `sse.ts`: stream start/resume and paid-run pointer only;
- `documents.ts`: upload/document/crawl/retry;
- `graph.ts`: entity search and inspect;
- `tables.ts`: list/analyze;
- `usage.ts`: member/company usage;
- `invitations.ts`: accept/create/offboard;
- `tools.ts`: registry seed/enable/permission;
- `knowledge.ts`: glossary and entity rules.

**Steps**

1. Extract one domain at a time, running `api.test.ts` after each.
2. Preserve endpoint, method, body, header, timeout, status, and parser behavior.
3. Keep stream response bodies unconsumed in
   `apps/frontend/src/lib/api/sse.ts`.
4. Update source-inspection tests to inspect owner modules, not only `api.ts`.
5. End with explicit exports in `api.ts`; do not use filesystem glob magic.

**Budgets:** barrel ≤100; each domain ≤300. Split `knowledge.ts` if it exceeds
300.

**Forbidden:** retries added to paid POST, hidden auth refresh, or SSE parsing in
the API layer.

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/lib/api.test.ts src/lib/prohibited-patterns.test.ts
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend typecheck
```

## MOD-04 — Extract citation and query ownership

**Objective:** reduce `chat-app.tsx` by moving presentation and query lifecycle,
with no stream ownership change.

**Add**

- `apps/frontend/src/components/chat/citation-drawer.tsx`;
- `apps/frontend/src/components/chat/hooks/use-chat-queries.ts`;
- focused tests beside each owner.

**Move to `citation-drawer.tsx`**

- exported `CitationDrawer`;
- citation-only rendering and props;
- no fetch/query behavior.

**Move to `use-chat-queries.ts`**

- `/meta`, `/me`, readiness, conversations, messages, usage, citations queries;
- query-key factories and derived loading/error/data values;
- history pagination data normalization, but not DOM scroll anchoring;
- query invalidations that are not part of a live stream.

**Hook contract**

```typescript
export type UseChatQueriesInput = {
  accessToken: string | null;
  conversationId: string | null;
  runId: string | null;
  terminal: boolean;
};

export type UseChatQueriesResult = {
  keys: ReturnType<typeof sessionQueryKeys>;
  currentUser: CurrentUserResponse | null;
  conversations: readonly ConversationResponse[];
  messages: readonly ConversationMessage[];
  citations: readonly CitationResponse[];
  // Explicit pending/error/refetch fields; no opaque bag.
};
```

Use the repository's actual auth wrapper types after inspection; the sketch is
not permission to invent duplicate types.

**Done when:** `chat-app.tsx` is smaller, render behavior is unchanged, and the
hook owns no `ReadableStream`, `AbortController`, SSE frame, or reconnect timer.

## MOD-05 — Extract the single chat-run controller

**Objective:** create one owner for send/resume/reconnect/cancel and leave the
existing `consumeSse` + `applySseFrame` engine intact.

**Add**

- `apps/frontend/src/components/chat/hooks/use-chat-run.ts`;
- `apps/frontend/src/components/chat/hooks/use-chat-run.test.ts`.

**Move**

- send lock and idempotency key lifecycle;
- persisted paid-run pointer;
- `AbortController`;
- automatic/manual resume;
- reconnect attempt and retry timer;
- cancellation;
- `ChatViewState` reducer publication;
- latest run/sequence/failure refs.

**Public result**

```typescript
export type UseChatRunResult = {
  chat: ChatViewState;
  sending: boolean;
  disconnected: boolean;
  reconnectAttempt: number;
  reconnectExhausted: boolean;
  nextRetryMs: number | null;
  send(text: string): Promise<boolean>;
  reconnect(): Promise<void>;
  cancel(): Promise<void>;
  resetRun(reason: "new-send" | "conversation-switch" | "sign-out"): void;
};
```

**Rules**

- only this hook calls `startOrResumeMessageStream`, `resumeEventStream`, and
  `consumeSse`;
- it never parses bytes or frames itself;
- `resetRun` aborts and clears timers before resetting;
- retry uses latest refs;
- terminal/replay/idempotency semantics remain unchanged.

**Tests:** successful send, synchronous POST response, interrupted stream,
resume after sequence, non-OK resume, deleted run, cancellation, sign-out,
conversation switch, double-click send, and unmount cleanup.

**Budget:** hook ≤300. Split persistence into
`apps/frontend/src/lib/paid-run-pointer.ts` if required; do not compress.

## MOD-06 — Make ChatApp composition-only and enforce budgets

**Objective:** reduce `chat-app.tsx` from 1201 to ≤300 lines before adding
streaming presentation features.

**Allowed new owners when needed**

- `apps/frontend/src/components/chat/chat-workspace.tsx`: layout and prop
  composition;
- `apps/frontend/src/components/chat/chat-banners.tsx`: safe failure/status
  banners;
- `apps/frontend/src/components/chat/hooks/use-conversation-actions.ts`:
  create/delete/load older;
- `apps/frontend/src/components/chat/hooks/use-chat-selection.ts`: selected IDs
  and reset policy.

**Final `ChatApp` responsibilities**

1. obtain auth/session context;
2. call `useChatQueries` and `useChatRun`;
3. compose rail, workspace, dialogs, and citation drawer;
4. pass typed props.

It must not own fetch, SSE, retry timers, pagination algorithms, modal focus
logic, or answer reveal scheduling.

**Add** `apps/frontend/src/lib/architecture-budget.test.ts` that checks:

- `chat-app.tsx` ≤300 physical lines;
- `api.ts` and `types.ts` ≤100;
- chat hooks and new modules ≤300;
- `chat-app.tsx` does not import `consumeSse`, stream API functions, or raw
  `fetch`;
- exactly one source owner imports `consumeSse` for chat-run transport.

Use the global physical-line metric from the execution contract. Blank lines,
comments, and documentation count; generated/vendor files are the only
reviewable exclusions.

**Commands**

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/lib/architecture-budget.test.ts src/components/chat-app.test.tsx
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend typecheck
```

**Stop:** if behavior tests fail during an extraction, revert that extraction
before starting another. Do not add progress/reveal code to make tests pass.

After MOD-06, continue with the verified remaining-source inventory and
MOD-07–MOD-19 dependencies in
[`08-remaining-modularization-packets.md`](./08-remaining-modularization-packets.md).
Before backend progress behavior, run BMOD-01–BMOD-09 from
[`02b-backend-modularization-packets.md`](./02b-backend-modularization-packets.md).
