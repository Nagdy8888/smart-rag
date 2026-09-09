/**
 * Pure chat-run view state. UI applies SSE frames without restarting paid work
 * on reconnect.
 */

import { displayText } from "./safe-text";
import {
  isKnownSseEvent,
  parseSsePayload,
  sequenceFromFrame,
  type SseFrame,
} from "./sse";
import { shouldShowCitations } from "./answer-origin";
import type { ApiFailure } from "./api";
import {
  applyProgressFrame,
  emptyRunProgress,
  type RunProgressState,
} from "./run-progress";
import type { RequestedSearchScope } from "./types";

/** Developer-visible diagnostics collected from catalog events. */
export type ChatDiagnostics = {
  requestedRoute: string | null;
  effectiveRoute: string | null;
  correctedRoute: string | null;
  correctionReason: string | null;
  limitationCodes: string[];
  cacheStatus: string | null;
  coverageScore: number | null;
  toolKeys: string[];
  citationIds: string[];
  promptTokens: number;
  completionTokens: number;
  /** Billed USD for the current run when the usage event includes it. */
  costUsd: number | null;
  heartbeatCount: number;
  unknownEvents: string[];
  strayCitationsHidden: number;
};

/** One Auto chat run as rendered by the thin UI. */
export type ChatViewState = {
  runId: string | null;
  reservationId: string | null;
  routeFamily: string | null;
  lastSequence: number;
  answerText: string;
  stage: string | null;
  status: string | null;
  terminal: string | null;
  diagnostics: ChatDiagnostics;
  failure: ApiFailure | null;
  idempotencyKey: string;
  answerOrigin: string | null;
  clarificationRequired: boolean;
  progress: RunProgressState;
  /** Client source preference echoed from admission or run fetch. */
  requestedSearchScope: RequestedSearchScope | null;
  /** Completed prior runs and title tokens in this live conversation. */
  chatPromptTokens: number;
  /** Completed prior runs and title tokens in this live conversation. */
  chatCompletionTokens: number;
  /** Billed USD from completed prior runs in this live conversation. */
  chatCostUsd: number;
};

/**
 * Return empty diagnostics.
 *
 * @returns Zeroed diagnostic mapping.
 */
export function emptyDiagnostics(): ChatDiagnostics {
  return {
    requestedRoute: null,
    effectiveRoute: null,
    correctedRoute: null,
    correctionReason: null,
    limitationCodes: [],
    cacheStatus: null,
    coverageScore: null,
    toolKeys: [],
    citationIds: [],
    promptTokens: 0,
    completionTokens: 0,
    costUsd: null,
    heartbeatCount: 0,
    unknownEvents: [],
    strayCitationsHidden: 0,
  };
}

/**
 * Create initial chat view state with a stable idempotency key.
 *
 * @param idempotencyKey - Client-generated UUID reused across retry.
 * @returns Empty run state.
 */
export function createChatViewState(idempotencyKey: string): ChatViewState {
  return {
    runId: null,
    reservationId: null,
    routeFamily: null,
    lastSequence: 0,
    answerText: "",
    stage: null,
    status: null,
    terminal: null,
    diagnostics: emptyDiagnostics(),
    failure: null,
    idempotencyKey,
    answerOrigin: null,
    clarificationRequired: false,
    progress: emptyRunProgress(),
    requestedSearchScope: null,
    chatPromptTokens: 0,
    chatCompletionTokens: 0,
    chatCostUsd: 0,
  };
}

/**
 * Start a new question while keeping this conversation's token totals.
 *
 * Prior run usage is folded into `chatPromptTokens` / `chatCompletionTokens`
 * so Run Details can show both this question and the whole chat.
 *
 * @param previous - Terminal or empty view from the same conversation.
 * @param idempotencyKey - Client key for the next admit.
 * @returns Empty run state that still carries conversation token totals.
 */
export function startNextChatRun(
  previous: ChatViewState,
  idempotencyKey: string,
): ChatViewState {
  const next = createChatViewState(idempotencyKey);
  return {
    ...next,
    chatPromptTokens: previous.chatPromptTokens + previous.diagnostics.promptTokens,
    chatCompletionTokens:
      previous.chatCompletionTokens + previous.diagnostics.completionTokens,
    chatCostUsd: previous.chatCostUsd + (previous.diagnostics.costUsd ?? 0),
  };
}

/**
 * Add billed tokens that are not part of the current query-run SSE envelope.
 *
 * Used for `POST /conversations/{id}/title` provider usage.
 *
 * @param state - Current view.
 * @param promptTokens - Provider prompt tokens to add. Negative values are ignored.
 * @param completionTokens - Provider completion tokens to add. Negative values are ignored.
 * @returns View with conversation totals increased.
 */
export function addChatTokens(
  state: ChatViewState,
  promptTokens: number,
  completionTokens: number,
): ChatViewState {
  const prompt = Number.isFinite(promptTokens) && promptTokens > 0 ? promptTokens : 0;
  const completion =
    Number.isFinite(completionTokens) && completionTokens > 0 ? completionTokens : 0;
  if (prompt === 0 && completion === 0) {
    return state;
  }
  return {
    ...state,
    chatPromptTokens: state.chatPromptTokens + prompt,
    chatCompletionTokens: state.chatCompletionTokens + completion,
  };
}

/**
 * Conversation-wide prompt and completion tokens for the live Ask session.
 *
 * Sums completed prior runs, the session title, and the current run.
 *
 * @param state - Current view.
 * @returns Prompt and completion totals for this chat.
 */
export function chatTokenTotals(state: ChatViewState): {
  promptTokens: number;
  completionTokens: number;
} {
  return {
    promptTokens: state.chatPromptTokens + state.diagnostics.promptTokens,
    completionTokens: state.chatCompletionTokens + state.diagnostics.completionTokens,
  };
}

/**
 * Conversation-wide billed USD for the live Ask session.
 *
 * @param state - Current view.
 * @returns Run totals plus any completed prior runs in this chat.
 */
export function chatCostTotal(state: ChatViewState): number {
  return state.chatCostUsd + (state.diagnostics.costUsd ?? 0);
}

/**
 * Apply admission JSON fields when the POST returns 202 instead of a stream.
 *
 * @param state - Current view.
 * @param admission - Packet-6 JSON body.
 * @returns Updated view.
 */
export function applyAdmission(
  state: ChatViewState,
  admission: {
    run_id: string;
    reservation_id: string;
    route_family: string;
    reconnect: boolean;
    requested_search_scope?: RequestedSearchScope;
  },
): ChatViewState {
  return {
    ...state,
    runId: admission.run_id,
    reservationId: admission.reservation_id,
    routeFamily: admission.route_family,
    requestedSearchScope: admission.requested_search_scope ?? state.requestedSearchScope,
    diagnostics: {
      ...state.diagnostics,
      requestedRoute: admission.route_family,
      effectiveRoute: admission.route_family,
    },
  };
}

function stringField(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return typeof value === "string" ? displayText(value) : null;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => displayText(String(item)));
}

/**
 * Return whether the run already has user-visible answer tokens.
 *
 * @param state - Current view.
 * @returns True when trimmed `answerText` is non-empty.
 */
export function hasKeptAnswer(state: ChatViewState): boolean {
  return state.answerText.trim() !== "";
}

/**
 * Return whether Ask chrome should render the run-failure StatusBanner.
 *
 * Partial terminals and errors that already kept tokens use AnswerSurface
 * only so the user sees exactly one alert.
 *
 * @param state - Current view.
 * @returns True when a protocol/server failure has no kept answer.
 */
export function shouldShowChatFailureBanner(state: ChatViewState): boolean {
  return state.failure !== null && !hasKeptAnswer(state);
}

/**
 * Apply one SSE frame. Unknown types are logged and skipped.
 *
 * @param state - Current view.
 * @param frame - Parsed SSE frame.
 * @returns Next view. The first terminal wins; later terminals and
 *   token deltas are ignored.
 */
export function applySseFrame(state: ChatViewState, frame: SseFrame): ChatViewState {
  const payload = parseSsePayload(frame.data);
  const sequence = sequenceFromFrame(frame, payload);
  if (sequence !== null && sequence <= state.lastSequence) {
    return state;
  }
  const lastSequence =
    sequence !== null && sequence > state.lastSequence ? sequence : state.lastSequence;

  if (!isKnownSseEvent(frame.event)) {
    const unknownEvents = [...state.diagnostics.unknownEvents, frame.event];
    return {
      ...state,
      lastSequence,
      diagnostics: { ...state.diagnostics, unknownEvents },
    };
  }

  if (state.terminal !== null) {
    return { ...state, lastSequence };
  }

  const next: ChatViewState = { ...state, lastSequence };
  const diagnostics = { ...state.diagnostics };
  next.progress = applyProgressFrame(
    state.progress,
    frame.event,
    payload,
    lastSequence,
    state.terminal !== null,
  );

  switch (frame.event) {
    case "status":
      next.stage = stringField(payload, "stage");
      next.status = stringField(payload, "status");
      break;
    case "heartbeat":
      diagnostics.heartbeatCount += 1;
      break;
    case "route_correction":
      diagnostics.requestedRoute =
        stringField(payload, "from_route") ?? diagnostics.requestedRoute;
      diagnostics.correctedRoute = stringField(payload, "to_route");
      diagnostics.effectiveRoute =
        diagnostics.correctedRoute ?? diagnostics.effectiveRoute;
      diagnostics.correctionReason = stringField(payload, "reason");
      break;
    case "limitation": {
      const code = stringField(payload, "code");
      if (code && !diagnostics.limitationCodes.includes(code)) {
        diagnostics.limitationCodes = [...diagnostics.limitationCodes, code];
      }
      break;
    }
    case "cache":
      diagnostics.cacheStatus = stringField(payload, "status");
      break;
    case "coverage": {
      const score = payload.coverage_score;
      diagnostics.coverageScore = typeof score === "number" ? score : null;
      break;
    }
    case "optional_tool_disclosure":
      diagnostics.toolKeys = stringList(payload.tool_keys);
      break;
    case "citation_preview":
      diagnostics.citationIds = stringList(payload.citation_ids);
      if (!shouldShowCitations(next.answerOrigin) && diagnostics.citationIds.length > 0) {
        diagnostics.strayCitationsHidden = diagnostics.citationIds.length;
      }
      break;
    case "answer_origin": {
      const raw = stringField(payload, "origin");
      if (raw) {
        next.answerOrigin = raw;
        next.clarificationRequired = raw === "ambiguous";
        if (!shouldShowCitations(raw) && diagnostics.citationIds.length > 0) {
          diagnostics.strayCitationsHidden = diagnostics.citationIds.length;
        }
      }
      break;
    }
    case "token_delta":
      if (!next.progress.verificationCompleted) {
        next.failure = { kind: "protocol", detail: "unverified_token_delta" };
        break;
      }
      next.answerText = `${state.answerText}${displayText(stringField(payload, "delta") ?? "")}`;
      break;
    case "usage":
      diagnostics.promptTokens =
        typeof payload.prompt_tokens === "number" ? payload.prompt_tokens : 0;
      diagnostics.completionTokens =
        typeof payload.completion_tokens === "number" ? payload.completion_tokens : 0;
      diagnostics.costUsd =
        typeof payload.cost_usd === "number" && Number.isFinite(payload.cost_usd)
          ? payload.cost_usd
          : null;
      break;
    case "deadline":
      next.stage = "deadline";
      break;
    case "schema":
      break;
    case "completed":
    case "cancelled":
    case "error":
    case "partial":
      next.terminal = frame.event;
      if (frame.event === "partial") {
        next.status = stringField(payload, "reason") ?? stringField(payload, "code");
      }
      if (frame.event === "error") {
        next.status = stringField(payload, "code") ?? stringField(payload, "reason");
        if (!hasKeptAnswer(state)) {
          next.failure = {
            kind: "protocol",
            detail: next.status ?? "run_error",
          };
        }
      }
      if (frame.event === "completed") {
        const refusal = stringField(payload, "refusal");
        if (state.answerText.trim() === "" && (refusal === null || refusal.trim() === "")) {
          next.terminal = "error";
          next.status = "empty_answer";
          next.failure = { kind: "protocol", detail: "empty_answer" };
        }
      }
      break;
    default:
      break;
  }

  next.diagnostics = diagnostics;
  return next;
}

/**
 * Build the resume query after disconnect. Never starts a second paid run.
 *
 * @param state - Current view.
 * @returns `after` sequence to pass to GET `/runs/{id}/events`.
 */
export function resumeAfterSequence(state: ChatViewState): number {
  return state.lastSequence;
}
