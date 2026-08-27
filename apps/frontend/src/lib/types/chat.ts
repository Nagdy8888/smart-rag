/**
 * Conversation, run, citation, origin, and feedback OpenAPI types.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

/** `GET|POST /conversations` and `POST /conversations/{id}/title` item. */
export type ConversationResponse = {
  conversation_id: string;
  creator_user_id: string;
  title: string | null;
  created_at: string | null;
  /** Provider prompt tokens. Set on title POST; 0/omitted on list/get/create. */
  prompt_tokens?: number;
  /** Provider completion tokens. Set on title POST; 0/omitted on list/get/create. */
  completion_tokens?: number;
};

/** One `GET /conversations/{id}/messages` item. Content is escaped text. */
export type ConversationMessage = {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

/** Keyset page from `GET /conversations/{id}/messages`. */
export type ConversationMessagesResponse = {
  items: ConversationMessage[];
  next_before_id: string | null;
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

/** `GET /runs/{run_id}` and `POST /runs/{run_id}/cancel` body. */
export type RunResponse = {
  run_id: string;
  conversation_id: string;
  creator_user_id: string;
  status: string;
  reservation_id: string | null;
  created_at: string | null;
};

/** `POST /runs/{run_id}/feedback` 201 body. */
export type FeedbackResponse = {
  feedback_id: string;
};

/** `GET /runs/{id}/citations` item. */
export type CitationResponse = {
  citation_id: string;
  citation_index: number;
  chunk_id: string | null;
  provenance: Record<string, unknown>;
  source_unavailable: boolean;
};

export const ANSWER_ORIGINS = [
  "general_knowledge",
  "company_documents",
  "user_supplied_text",
  "deterministic",
  "ambiguous",
] as const;

/** One catalog answer origin. Unknown values are tolerated at the reducer. */
export type AnswerOrigin = (typeof ANSWER_ORIGINS)[number];

/** Exact unmerged thumbs-up tags. */
export const FEEDBACK_TAGS_UP = [
  "helpful answer",
  "accurate citation",
  "correct route",
  "correct calculation",
  "sufficient graph",
] as const;

/** Exact unmerged thumbs-down diagnostic tags. */
export const FEEDBACK_TAGS_DOWN = [
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

/** Union of polarity catalogs. Tags are never merged. */
export const FEEDBACK_TAGS = [
  ...FEEDBACK_TAGS_UP,
  ...FEEDBACK_TAGS_DOWN,
] as const;

export type FeedbackTag = (typeof FEEDBACK_TAGS)[number];

/**
 * Return the exact tag catalog for the selected thumb.
 *
 * @param thumbsUp - True after thumbs up.
 * @returns Unmerged tags for that polarity.
 */
export function feedbackTagsFor(thumbsUp: boolean): readonly FeedbackTag[] {
  return thumbsUp ? FEEDBACK_TAGS_UP : FEEDBACK_TAGS_DOWN;
}
