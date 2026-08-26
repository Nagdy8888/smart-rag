# Candidate Frontend Progress and Verified-Reveal Packets

Status: **candidate, non-canonical**

Prerequisites: GOV-00 integrity passes, then MOD-01 through MOD-06 and BEP-01
through BEP-07 pass. Extend the existing `consumeSse` + `applySseFrame` engine;
never create another parser or run reducer.

All FEP packets are hard-blocked until the superseding Phase 6/8 amendments and
integrity lock pass.

## FEP-01 — SSE types and pure progress reduction

**Objective:** make persisted server events reconstruct a route-aware timeline.

**Modify**

- after MOD-01, the newly extracted
  `apps/frontend/src/lib/types/sse.ts`;
- `apps/frontend/src/lib/chat-view.ts`;
- `apps/frontend/src/lib/chat-view.test.ts`.

**Add**

- `apps/frontend/src/lib/run-progress.ts`;
- `apps/frontend/src/lib/run-progress.test.ts`.

**Types**

```typescript
export type RunProgressPhase = "started" | "completed" | "failed";
export type RunProgressKind = "node" | "tool";

export type RunProgressItem = {
  id: string;
  kind: RunProgressKind;
  key: string;
  phase: RunProgressPhase;
  outcome: string | null;
  firstSequence: number;
  lastSequence: number;
};

export type RunProgressState = {
  items: readonly RunProgressItem[];
  lastSequence: number;
  verificationCompleted: boolean;
};
```

Add `tool_progress` to `KNOWN_SSE_EVENT_TYPES` only after the backend catalog is
merged.

**Reducer rules**

1. Ignore frames at or below `lastSequence`.
2. `status phase=started`: append one node item unless the latest same-key item
   is already open.
3. `status phase=completed|failed`: close the latest open same-key item; if no
   start exists, append a terminal item for legacy compatibility.
4. Legacy `status` without phase is a completed update.
5. `tool_progress` follows the same open/close rule by `tool_key`.
6. `optional_tool_disclosure` means selected/available only; it never creates an
   executed-tool row.
7. A completed `verify_answer` status sets `verificationCompleted`.
8. Protocol terminal freezes new progress additions; it does not rewrite a
   cancelled active item as successful.
9. Do not record client timestamps or durations.

`ChatViewState` owns this progress state. `applySseFrame` delegates to the pure
helper and remains the only frame-to-chat reducer entry point.

**Verified text fail-closed rule**

- Accept `token_delta` only after `verificationCompleted`.
- If a token arrives early, do not render or append it; expose the existing safe
  protocol-failure path and allow terminal handling.
- Preserve the backend's verified-final guarantee as the primary boundary.

**Tests**

- node started→completed;
- tool started→failed;
- duplicate and replayed sequence;
- completed without start;
- skipped stage absent;
- selected but unexecuted tool absent;
- early token fails closed;
- token after verify appends immediately to authoritative `answerText`;
- first terminal wins.

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/lib/run-progress.test.ts src/lib/chat-view.test.ts
pnpm --filter smart-rag-frontend typecheck
```

## FEP-02 — Truthful progress timeline

**Objective:** show actual node/tool work before answer prose so the user is not
waiting blindly.

**Add**

- `apps/frontend/src/components/chat/run-progress-timeline.tsx`;
- `apps/frontend/src/components/chat/run-progress-timeline.test.tsx`.

**Preserve/migrate**

- `apps/frontend/src/components/chat/run-progress.tsx`, which currently exports
  only `runStatusLine()`;
- `apps/frontend/src/components/chat/answer-surface.tsx`.

Keep `runStatusLine()` working during migration. At integration, render one
summary inside `RunProgressTimeline` and remove the old separate status-line
render from `ChatApp`/`AnswerSurface`; do not leave two competing status
surfaces.

**Component contract**

```typescript
export type RunProgressTimelineProps = {
  items: readonly RunProgressItem[];
  terminal: ChatTerminalState | null;
  verificationCompleted: boolean;
  answerAvailable: boolean;
  collapsed: boolean;
};
```

Use actual repository terminal types after inspection.

**Rendering**

- render only items present in reducer state;
- map known internal keys to concise labels in a pure label table;
- retain raw key in accessible details/debug copy, not as unsafe HTML;
- active `started` row gets spinner and `aria-current="step"`;
- completed/failed rows receive distinct icon and text, not color alone;
- fast adjacent start/completion remains visible as completed history;
- tool rows are nested/grouped under the optional-tools stage only when emitted;
- before answer availability, timeline remains expanded;
- after reveal completes, collapse to a summary button while preserving all
  rows;
- never show a fake percentage or elapsed duration.

**Truthful status copy**

- before verify: current server stage label;
- verify completed but no text: `Verified — preparing display`;
- reveal active: `Verified — displaying answer`;
- reveal complete: `Verified answer`;
- terminal failure/cancel: existing safe failure copy.

**Accessibility**

- timeline uses `role="list"` and rows `role="listitem"`;
- announce meaningful stage changes in one polite live region;
- do not announce every answer slice;
- collapse button exposes `aria-expanded`;
- no spinner-only label.

**Tests**

- company fixture shows only emitted stages/tools;
- general fixture has no company retrieval/tool rows;
- no assistant prose before verified token;
- unknown safe stage gets deterministic fallback label;
- keyboard can expand/collapse;
- no client-created timestamp/percentage text.

```powershell
pnpm --filter smart-rag-frontend exec vitest run src/components/chat/run-progress-timeline.test.tsx src/components/chat/answer-surface.test.tsx src/components/chat-app.test.tsx
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend typecheck
```

## FEP-03 — Unicode-safe reveal engine

**Objective:** progressively display already verified text without coupling
animation to transport chunks.

**Add**

- `apps/frontend/src/lib/verified-answer-segment.ts`;
- `apps/frontend/src/lib/verified-answer-segment.test.ts`;
- `apps/frontend/src/components/chat/hooks/use-verified-answer-reveal.ts`;
- `apps/frontend/src/components/chat/hooks/use-verified-answer-reveal.test.ts`.

**Segmentation**

```typescript
export function segmentVerifiedText(text: string): readonly string[];
```

Use `new Intl.Segmenter("und", { granularity: "grapheme" })`. If unavailable or
construction fails, return `[text]`; never slice UTF-16 manually.

Test Arabic, combining marks, emoji ZWJ/family/flags, bidirectional text,
newlines, Markdown punctuation, and citation brackets by asserting joined
segments exactly equal input.

**Hook contract**

```typescript
export type VerifiedRevealInput = {
  presentationKey: string; // conversation ID + run ID, no secret
  authoritativeText: string;
  animate: boolean; // current run created in this mounted session
  reducedMotion: boolean;
};

export type VerifiedRevealResult = {
  visibleText: string;
  isRevealing: boolean;
  isComplete: boolean;
  publicationCount: number; // development/test diagnostics only
  showFullAnswer(): void;
};
```

`animate` must not become false merely because the protocol terminal arrived.
Terminal persistence and the presentation state are independent.

**Scheduler**

1. Empty text → empty/idle.
2. Historical/reloaded or reduced-motion → full text immediately.
3. ≤80 graphemes → full text on the next animation frame.
4. >80 graphemes:
   - first render keeps the prior visible prefix;
   - first animation frame publishes a strict partial prefix;
   - at least one later paint publishes more/full text;
   - choose each batch with
     `ceil(remaining / min(publicationsLeft, estimatedFramesLeft))`;
   - hard deadline is 2500 ms from first non-empty verified availability;
   - cap reveal-owned state publications at 90;
   - at deadline/cap, return full current authoritative text.
5. If authoritative text grows, re-segment and continue from the exact visible
   grapheme prefix; never restart.
6. If a late verified chunk arrives after deadline/cap, expose it immediately
   without restarting an animation.
7. Cancel rAF on key change, new send, switch, sign-out, skip, or unmount.

Do not persist the presentation cursor. Do not alter SSE sequence or reducer
state. Do not use `setInterval`, per-character delay, backend sleeps, or a
typewriter caret.

**Tests with mocked rAF/performance clock**

- long answer has strict partial intermediate state and at least two paints;
- completes by 2500 ms;
- never exceeds 90 reveal publications;
- `showFullAnswer` is synchronous;
- reduced motion/historical is immediate;
- growing target preserves prefix;
- key change and unmount cancel callbacks;
- no broken grapheme.

## FEP-04 — Reveal presentation and integration

**Objective:** wire the reveal into the answer surface while every protocol and
data operation continues immediately.

**Add**

- `apps/frontend/src/components/chat/verified-answer-reveal.tsx`;
- focused component test.

**Modify**

- `apps/frontend/src/components/chat/answer-surface.tsx`;
- `apps/frontend/src/components/chat/hooks/use-chat-run.ts`;
- thin `apps/frontend/src/components/chat/chat-app.tsx`;
- `apps/frontend/src/components/chat-app.test.tsx`.

**Rules**

- `chat.answerText` remains the complete authoritative verified buffer;
- current live assistant renders `visibleText`;
- historical messages render full content directly and never replay animation;
- citations, terminal banner, usage settlement UI, persistence, reconnect
  cursor, feedback eligibility, and next-send controls read authoritative
  state; none waits for reveal;
- `Show full answer` calls `showFullAnswer`;
- pointer selection/copy intent while revealing calls `showFullAnswer` before
  native selection/copy continues;
- new send/switch/sign-out completes old reveal, then resets key;
- answer region uses existing safe text renderer; no `dangerouslySetInnerHTML`.

**Screen reader behavior**

- announce `Verified answer ready` once when non-empty verified text first
  becomes available;
- answer slices themselves are not a live region;
- skip button is keyboard reachable;
- reduced-motion users see full text.

**Deterministic component fixture**

This is a **company-route** fixture. General/mixed fixtures must not require
`generate_answer`.

```text
status generate_answer started
status generate_answer completed
status verify_answer started
status verify_answer completed
token_delta <long verified part>
completed
```

Assert no prose through verify start, then an intermediate prefix, then the full
answer; terminal/citation actions must already be available during the reveal.

## FEP-05 — Conversation pinning and reveal growth

**Objective:** follow visible answer growth only while the user remains near the
bottom.

**Add**

- `apps/frontend/src/components/chat/hooks/use-conversation-scroll.ts`;
- focused hook tests.

**Contract**

- pinned when distance from bottom ≤48 px;
- wheel/touch/manual upward scroll unpins;
- visible-text growth scrolls only when pinned;
- `Jump to latest` re-pins and scrolls;
- loading earlier captures pre-render `scrollHeight` and restores the anchor by
  height delta;
- conversation switch aborts/ignores an older pagination request;
- load-earlier failure shows retryable safe copy;
- never scroll `window`, `#main`, or the session rail.

Use `useLayoutEffect` only for measured anchor correction, with a documented
reason. Batch reads before writes.

**Tests:** pin threshold, unpin, reveal growth, jump, prepend anchor,
conversation switch, and pagination failure.
