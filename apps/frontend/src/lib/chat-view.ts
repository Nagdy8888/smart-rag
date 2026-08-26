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
  };
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
  },
): ChatViewState {
  return {
    ...state,
    runId: admission.run_id,
    reservationId: admission.reservation_id,
    routeFamily: admission.route_family,
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
