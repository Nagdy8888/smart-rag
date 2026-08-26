/**
 * Pure reduction of persisted SSE frames into a route-aware progress timeline.
 *
 * This helper does not parse SSE text. `applySseFrame` remains the only
 * frame-to-chat entry point.
 */

import type { SseProgressPhase } from "./types/sse";

/** Wire-aligned progress phase used by the timeline. */
export type RunProgressPhase = SseProgressPhase;

/** Timeline row kind. Disclosure events never create a tool row. */
export type RunProgressKind = "node" | "tool";

/** One node or executed-tool row reconstructed from persisted events. */
export type RunProgressItem = {
  id: string;
  kind: RunProgressKind;
  key: string;
  phase: RunProgressPhase;
  outcome: string | null;
  firstSequence: number;
  lastSequence: number;
};

/** Replay-safe progress owned by `ChatViewState`. */
export type RunProgressState = {
  items: readonly RunProgressItem[];
  lastSequence: number;
  verificationCompleted: boolean;
};

const VERIFY_STAGE = "verify_answer";

/**
 * Return an empty progress timeline.
 *
 * @returns Zeroed progress with no items.
 */
export function emptyRunProgress(): RunProgressState {
  return {
    items: [],
    lastSequence: 0,
    verificationCompleted: false,
  };
}

function latestOpenIndex(
  items: readonly RunProgressItem[],
  kind: RunProgressKind,
  key: string,
): number {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    if (item && item.kind === kind && item.key === key && item.phase === "started") {
      return index;
    }
  }
  return -1;
}

function closeOrAppend(
  items: readonly RunProgressItem[],
  kind: RunProgressKind,
  key: string,
  phase: Exclude<RunProgressPhase, "started">,
  outcome: string | null,
  sequence: number,
): RunProgressItem[] {
  const open = latestOpenIndex(items, kind, key);
  if (open >= 0) {
    const current = items[open];
    if (!current) {
      return [...items];
    }
    const next = [...items];
    next[open] = {
      ...current,
      phase,
      outcome,
      lastSequence: sequence,
    };
    return next;
  }
  return [
    ...items,
    {
      id: `${kind}:${key}:${String(sequence)}`,
      kind,
      key,
      phase,
      outcome,
      firstSequence: sequence,
      lastSequence: sequence,
    },
  ];
}

/**
 * Apply one known catalog event to progress state.
 *
 * @param progress - Current timeline.
 * @param event - Catalog event name.
 * @param payload - Parsed JSON object.
 * @param sequence - Persisted frame sequence.
 * @param frozen - True when a protocol terminal already won.
 * @returns Next progress. Sequences at or below `lastSequence` are ignored.
 */
export function applyProgressFrame(
  progress: RunProgressState,
  event: string,
  payload: Record<string, unknown>,
  sequence: number,
  frozen: boolean,
): RunProgressState {
  if (sequence <= progress.lastSequence) {
    return progress;
  }
  const lastSequence = sequence;
  if (frozen) {
    return { ...progress, lastSequence };
  }
  if (event === "optional_tool_disclosure") {
    return { ...progress, lastSequence };
  }
  if (
    event === "completed" ||
    event === "cancelled" ||
    event === "error" ||
    event === "partial"
  ) {
    return { ...progress, lastSequence };
  }
  if (event === "tool_progress") {
    const toolKey = typeof payload.tool_key === "string" ? payload.tool_key : "";
    const phase = payload.phase;
    if (!toolKey || (phase !== "started" && phase !== "completed" && phase !== "failed")) {
      return { ...progress, lastSequence };
    }
    if (phase === "started") {
      const open = latestOpenIndex(progress.items, "tool", toolKey);
      if (open >= 0) {
        return { ...progress, lastSequence };
      }
      return {
        ...progress,
        lastSequence,
        items: [
          ...progress.items,
          {
            id: `tool:${toolKey}:${String(sequence)}`,
            kind: "tool",
            key: toolKey,
            phase: "started",
            outcome: null,
            firstSequence: sequence,
            lastSequence: sequence,
          },
        ],
      };
    }
    return {
      ...progress,
      lastSequence,
      items: closeOrAppend(progress.items, "tool", toolKey, phase, phase, sequence),
    };
  }
  if (event !== "status") {
    return { ...progress, lastSequence };
  }
  const stage = typeof payload.stage === "string" ? payload.stage : "";
  if (!stage) {
    return { ...progress, lastSequence };
  }
  const rawPhase = payload.phase;
  const phase: RunProgressPhase =
    rawPhase === "started" || rawPhase === "completed" || rawPhase === "failed"
      ? rawPhase
      : "completed";
  const outcome = typeof payload.status === "string" ? payload.status : null;
  let items = progress.items;
  if (phase === "started") {
    const open = latestOpenIndex(items, "node", stage);
    if (open < 0) {
      items = [
        ...items,
        {
          id: `node:${stage}:${String(sequence)}`,
          kind: "node",
          key: stage,
          phase: "started",
          outcome,
          firstSequence: sequence,
          lastSequence: sequence,
        },
      ];
    }
  } else {
    items = closeOrAppend(items, "node", stage, phase, outcome, sequence);
  }
  const verificationCompleted =
    progress.verificationCompleted ||
    (stage === VERIFY_STAGE && (phase === "completed" || phase === "failed"));
  return {
    items,
    lastSequence,
    verificationCompleted,
  };
}
