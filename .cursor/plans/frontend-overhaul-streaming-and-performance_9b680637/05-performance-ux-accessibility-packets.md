# Candidate Performance, UX, and Accessibility Packets

Status: **candidate, non-canonical**

These packets follow the modular seams. They do not modify the streaming
protocol.

## PER-01 — Coalesce stream publications without losing events

**Objective:** reduce render amplification while preserving the complete
timeline.

**Modify**

- `apps/frontend/src/lib/sse-consume.ts`;
- `apps/frontend/src/lib/sse-consume.test.ts`;
- `apps/frontend/src/components/chat/hooks/use-chat-run.ts`;
- `apps/frontend/src/components/chat/hooks/use-chat-run.test.ts`.

For each `reader.read()` result:

1. parse all complete frames;
2. reduce every frame synchronously in sequence;
3. stop at first terminal as today;
4. call `onState(current)` once for that read batch, or once at terminal;
5. preserve last sequence/run filtering and parser remainder.

Do not drop intermediate progress items: the reducer's final state must retain
the full started/completed history even if React receives one publication.
For a heartbeat-only batch, retain the updated sequence in the run controller's
cursor ref/persisted pointer through this explicit optional callback added after
the existing `onState` parameter:

```typescript
onCursor?: (lastSequence: number) => void;
```

Invoke it once whenever an accepted batch advances the sequence, including
heartbeat-only batches. `useChatRun` updates its latest cursor ref and existing
bounded pointer persistence without calling React state. Existing callers may
omit the callback. Resume may never regress because a render was suppressed.

**Tests:** multiple frames in one byte chunk, frame split across reads, terminal
in the middle, malformed/foreign run, identical reconstructed verified answer,
and a heartbeat-only read batch that causes no React state publication.

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/lib/sse-consume.test.ts src/lib/chat-view.test.ts src/lib/run-progress.test.ts
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend typecheck
```

## PER-02 — Deduplicate role-aware readiness

**Objective:** one cache entry and one polling request per session-role tuple.

**Add:** `apps/frontend/src/lib/hooks/use-console-readiness.ts`.
Also add
`apps/frontend/src/lib/hooks/use-console-readiness.test.ts`.

**Modify**

- `apps/frontend/src/lib/query-keys.ts`;
- `apps/frontend/src/components/chat/hooks/use-chat-queries.ts`;
- `apps/frontend/src/components/ui/readiness-indicator.tsx`;
- `apps/frontend/src/components/admin/usage-panel.tsx`;
- focused tests.

**Canonical key**

```typescript
["console-ready", sessionScope, role ?? "pending"]
```

Expose it through `sessionQueryKeys`, not inline arrays. Raw token and UI-derived
role are forbidden. The role must come from `/me`.

The shared hook owns:

- `loadConsoleReadiness(auth, role)`;
- enablement after session and role resolution;
- `staleTime: 30_000`;
- `refetchInterval: 15_000`;
- `refetchIntervalInBackground: false`.

Signed-out public readiness keeps its separate public key. Operator readiness
still depends on server-provided owner/admin role. Readiness is not an
authorization boundary.

**Tests:** mount shell/chat/usage consumers together, assert one request per key
within a polling interval; role transition creates the expected new key; sign
out clears private readiness.

## PER-03 — Numeric render, publication, and request ceilings

**Objective:** replace vague “make it faster” claims with deterministic budgets.

**Add/extend focused tests**

- `apps/frontend/src/lib/sse-consume.test.ts`;
- `apps/frontend/src/components/chat/hooks/use-verified-answer-reveal.test.ts`;
- `apps/frontend/src/components/chat-app.test.tsx`;
- the readiness hook test created by PER-02.

**Ceilings**

- SSE reducer publications are at most one per `reader.read()` batch plus the
  existing terminal flush;
- reveal-owned state publications are ≤90 for one answer;
- readiness network calls are one per unique session-role query key in a
  15-second interval, regardless of mounted consumers;
- after live streaming begins, unchanged conversation-rail rows render zero
  additional times; a selected-row state change may render only the affected
  row;
- no test asserts a total `ChatApp` commit count, which varies by React mode.

Instrument render counts only in tests through a small callback/profiler seam;
do not ship a production analytics dependency. Record before/after counts in
evidence.

**Stop:** if a target cannot be isolated deterministically under the current
test renderer, report it `UNVERIFIED` and create a profiling packet; do not
invent a passing threshold.

## UX-01 — Hydration-stable shell and 390px topbar

**Objective:** remove local-storage hydration mismatch and mobile collisions.

**Add:** `apps/frontend/src/lib/hooks/use-layout-preference.ts`, reusing the
existing constants/read/write functions in
`apps/frontend/src/lib/layout-preferences.ts`.

**Modify**

- `apps/frontend/src/components/ui/app-shell.tsx`;
- `apps/frontend/src/components/ui/app-nav.tsx`;
- `apps/frontend/src/components/ui/readiness-indicator.tsx`;
- `apps/frontend/src/components/ui/app-shell.module.css`;
- `apps/frontend/src/components/ui/app-shell.test.tsx`;
- `apps/frontend/tests/e2e/visual-routes.spec.ts`.

**Hydration contract**

- server snapshot and first client snapshot use `defaultNavExpanded()`;
- `useSyncExternalStore` reads persisted preference after hydration;
- same-tab writes notify a custom subscription; cross-tab `storage` events also
  notify;
- the hook imports and extends `layout-preferences.ts`; it does not duplicate
  storage keys or parsing;
- `suppressHydrationWarning` is not the fix;
- no auth/session information is stored in this preference.

**Mobile contract at 390px and 200% zoom**

- hide duplicate topbar brand below desktop breakpoint;
- title has `min-width: 0`, truncation, and a bounded flex share;
- menu, account, and readiness remain reachable with ≥36px targets;
- compact readiness uses icon/short text plus screen-reader full copy;
- no horizontal overflow or vertical single-letter status;
- do not remove readiness on mobile.

**Visual test**

Wait for a deterministic readiness and route-data state, not only `#main`.
Capture both 390px and desktop. Do not update baselines until hydration console
errors are zero and assertions pass.

## UX-02 — Truthful loading/error/empty states

**Objective:** never show success-empty copy while data is pending or forbidden.

**Primary path**

- `apps/frontend/src/components/tables/tables-app.tsx`;
- `apps/frontend/src/components/tables/tables-app.test.tsx`.

**Pattern for each query surface**

```text
pending without cached data -> labelled loading/skeleton
error                       -> safe error banner + retry
success with []             -> domain empty state
success with data           -> content
background refetch          -> keep cached content + subtle refresh
```

Apply first to table manifests and duplicate analyze-panel empty rendering.
Audit documents, graph, session rail, and admin lists; create a separate packet
for any additional behavior change rather than broad editing.

**Tests:** unresolved promise, 403, 500, empty array, cached-data refetch, and
success data. Error and empty copy must be mutually exclusive.

## UX-03 — Session-list semantics and safe delete

**Objective:** remove nested interactivity from listbox options and make delete
confirmable/failable.

**Modify**

- `apps/frontend/src/components/chat/conversation-rail.tsx`;
- its CSS;
- current conversation-action hook/owner;
- `apps/frontend/src/components/chat-app.test.tsx`.

**Semantics**

- use a semantic list/listitem;
- each row has one primary session-selection control;
- place the overflow/delete menu as a sibling, never inside a
  `role="option"` control;
- preserve arrow-key navigation only if it remains valid for the chosen widget;
- retain UUID-masking accessible names.

**Delete flow**

1. row/header delete opens existing `ConfirmDialog`;
2. copy uses safe session title or `Untitled chat`;
3. pending disables duplicate confirmation;
4. server DELETE success removes/invalidate scoped query;
5. deleting active conversation aborts run and resets local state;
6. non-success renders safe failure and keeps the row;
7. cancel performs no request.

**Tests:** no `[role=option] button` nesting, keyboard selection, menu access,
cancel, server failure, double click, and active-session success.

## UX-04 — Drawer, command menu, and menu focus parity

**Objective:** consistent modal/menu keyboard and scroll behavior.

**Inspect first:**

- `apps/frontend/src/components/ui/sheet.tsx`;
- `apps/frontend/src/components/ui/drawer.tsx`;
- `apps/frontend/src/components/ui/command-menu.tsx`;
- `apps/frontend/src/components/ui/menu.tsx`;
- their callers;
- `apps/frontend/src/components/ui/primitives.test.tsx`.

**Allowed new utilities**

- `apps/frontend/src/components/ui/focus-trap.ts`;
- `apps/frontend/src/components/ui/body-scroll-lock.ts`.

Keep each ≤100 lines and dependency-free.

**Drawer**

- visible backdrop;
- backdrop click closes;
- body scroll locked while open and restored exactly once;
- Tab/Shift+Tab wrap;
- Escape closes;
- focus returns to provided trigger.

**Command menu**

- initial focus moves to search/first actionable control;
- Tab trap and Escape;
- body scroll lock;
- restore `#shell-command` trigger;
- global shortcut does not fire while typing in an editable control.

**Menu**

- first enabled item focused on open;
- ArrowUp/Down wrap;
- Home/End;
- Escape and outside click close;
- focus returns to trigger;
- disabled items skipped.

**Tests:** nested lock acquisition/release, focus wrap both directions, restore,
backdrop, Home/End, and unmount cleanup.

**Forbidden:** a new UI dependency solely to avoid fixing these primitives,
positive-tabindex hacks, or duplicated focus-trap code.

## UX-05 — Keyboard-equivalent graph selection

**Objective:** every selectable graph node has a keyboard path.

**Modify**

- `apps/frontend/src/components/graph/graph-canvas.tsx`;
- `apps/frontend/src/components/graph/graph-explorer.tsx`;
- `apps/frontend/src/components/graph/graph-list-fallback.tsx`;
- `apps/frontend/src/components/graph/graph-explorer.test.tsx`.

**Steps**

1. Verify the pinned React Flow version and primary docs for node focus support.
2. Keep graph editing/dragging/connecting disabled.
3. Make focused canvas node Enter/Space call the same `onSelect` as pointer.
4. Expose selection with `aria-current` or selected state.
5. Keep List view the canonical fully accessible fallback and default.
6. If pinned React Flow cannot provide reliable node focus, label Canvas as a
   supplementary visualization and provide a visible `Open accessible list`
   action; do not claim canvas parity.

**Tests:** list selection, canvas focus+Enter/Space, inspector focus/return, and
no edit affordances.

## UX-06 — Load-earlier race and error state

**Objective:** pagination cannot write into a newly selected conversation.

**Modify:** the extracted conversation action/query hook and scroll hook.

Use an abort controller or monotonically increasing request token keyed by
conversation ID. Before applying a page, verify both token and current
conversation. Capture scroll anchor before request and restore only after the
matching page commits.

On failure, preserve existing messages and show retry. A stale completion or
failure is ignored.

**Tests:** rapid A→B switch, out-of-order completion, aborted request, retry,
empty final page, and anchor preservation.

## Packet-local command bundle

```powershell
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend typecheck
pnpm --filter smart-rag-frontend test
pnpm --filter smart-rag-frontend exec playwright test tests/e2e/visual-routes.spec.ts
pnpm --filter smart-rag-frontend exec playwright test tests/e2e/quality-audit.spec.ts
```

Run only relevant focused tests during iteration, then this bundle before the
selected UX packet is marked complete.
