/**
 * Catalog SSE event-name contracts.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

/** Catalog event names from the backend SSE catalog. */
export const KNOWN_SSE_EVENT_TYPES = [
  "schema",
  "status",
  "tool_progress",
  "heartbeat",
  "route_correction",
  "limitation",
  "deadline",
  "partial",
  "cache",
  "coverage",
  "optional_tool_disclosure",
  "citation_preview",
  "answer_origin",
  "token_delta",
  "usage",
  "completed",
  "cancelled",
  "error",
] as const;

export type KnownSseEventType = (typeof KNOWN_SSE_EVENT_TYPES)[number];

/** Wire-level progress phase. Legacy status rows omit this field. */
export type SseProgressPhase = "started" | "completed" | "failed";

export const TERMINAL_SSE_EVENT_TYPES = [
  "completed",
  "cancelled",
  "error",
  "partial",
] as const;
