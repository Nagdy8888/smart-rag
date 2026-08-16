/**
 * OpenAPI-aligned types for the thin developer UI.
 *
 * Field names match `docs/api/openapi.foundation.json`. This file does not
 * invent endpoints or payload keys.
 */

/** `GET /api/meta` handshake body. */
export type MetaResponse = {
  api_version: string;
  sse_schema_version: string;
  min_client_version: string;
};

/** `GET /me` server-derived identity. */
export type CurrentUserResponse = {
  user_id: string;
  role: string;
  authorization_version: number;
  upload_enabled: boolean;
  mfa_enrolled: boolean;
};

/** `GET|POST /conversations` item. */
export type ConversationResponse = {
  conversation_id: string;
  creator_user_id: string;
  title: string | null;
  created_at: string | null;
};

/** JSON 202 from `POST /conversations/{id}/messages`. */
export type SubmitMessageResponse = {
  run_id: string;
  stream_path: string;
  reconnect: boolean;
  reservation_id: string;
  route_family: string;
  status: string;
};

/** `GET /runs/{id}/citations` item. */
export type CitationResponse = {
  citation_id: string;
  citation_index: number;
  chunk_id: string | null;
  provenance: Record<string, unknown>;
  source_unavailable: boolean;
};

/** `GET /documents` item. */
export type DocumentResponse = {
  document_id: string;
  title: string | null;
  visibility: string;
  current_version_id: string | null;
  visibility_generation: number;
};

/** `GET /usage/me` totals without prompt text. */
export type UsageResponse = {
  scope: string;
  cost_usd: string | number;
  prompt_tokens: number;
  completion_tokens: number;
  usage_rows: number;
};

/** Catalog event names from `smart_rag_core.sse.catalog`. */
export const KNOWN_SSE_EVENT_TYPES = [
  "schema",
  "status",
  "heartbeat",
  "route_correction",
  "limitation",
  "deadline",
  "partial",
  "cache",
  "coverage",
  "optional_tool_disclosure",
  "citation_preview",
  "token_delta",
  "usage",
  "completed",
  "cancelled",
  "error",
] as const;

export type KnownSseEventType = (typeof KNOWN_SSE_EVENT_TYPES)[number];

export const TERMINAL_SSE_EVENT_TYPES = [
  "completed",
  "cancelled",
  "error",
  "partial",
] as const;

/** Exact unmerged packet-7 feedback tags. */
export const FEEDBACK_TAGS = [
  "chunk/cleaning loss",
  "profile field wrong",
  "candidate miss",
  "wrong rerank",
  "bad refusal/overconfident answer",
  "missed relationship",
  "wrong route",
  "wrong calculation",
  "bad citation",
  "insufficient graph",
] as const;

export type FeedbackTag = (typeof FEEDBACK_TAGS)[number];
