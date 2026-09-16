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
  /** Owning run when the message was persisted with a citation batch. */
  run_id?: string | null;
  /** ACL-rechecked citations for this message. Never fetched N+1 from history. */
  citations?: CitationResponse[];
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
  requested_search_scope: RequestedSearchScope;
};

/** `GET /runs/{run_id}` and `POST /runs/{run_id}/cancel` body. */
export type RunResponse = {
  run_id: string;
  conversation_id: string;
  creator_user_id: string;
  status: string;
  reservation_id: string | null;
  created_at: string | null;
  requested_search_scope: RequestedSearchScope;
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
  /** Catalog kind. Missing values parse as `company_document`. */
  source_kind?: string;
  /** Web evidence id when `source_kind` is `web`. */
  web_source_id?: string | null;
  /** 0–5 paragraph mapping, or null for legacy/unmapped rows. */
  paragraph_index?: number | null;
  /** ACL-safe document title. Never copied from `page_label`. */
  document_title?: string | null;
  /** 1-based PDF toolbar page from locators, or null when unknown. */
  pdf_page_number?: number | null;
  /** Exact supporting span. Top-level only; never read from provenance. */
  evidence_excerpt?: string | null;
};

export const ANSWER_ORIGINS = [
  "general_knowledge",
  "company_documents",
  "user_supplied_text",
  "deterministic",
  "ambiguous",
  "web",
] as const;

/** Client source preference. Not authorization and not answer origin. */
export const REQUESTED_SEARCH_SCOPES = [
  "auto",
  "company_documents",
  "general_knowledge",
  "web",
] as const;

/** One catalog answer origin. Unknown values are tolerated at the reducer. */
export type AnswerOrigin = (typeof ANSWER_ORIGINS)[number];

/** Source preference sent on paid POST and echoed on the admitted run. */
export type RequestedSearchScope = (typeof REQUESTED_SEARCH_SCOPES)[number];

/** Exact Ask dropdown labels. Origin banners use ``answerOriginLabel``. */
export const SEARCH_SCOPE_LABELS: Record<RequestedSearchScope, string> = {
  auto: "Auto",
  company_documents: "Company documents",
  general_knowledge: "General",
  web: "Web",
};

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

/**
 * Return whether a value is a known requested search scope.
 *
 * @param value - Untrusted string.
 * @returns True for the four catalog values.
 */
export function isRequestedSearchScope(
  value: string,
): value is RequestedSearchScope {
  return (REQUESTED_SEARCH_SCOPES as readonly string[]).includes(value);
}

/**
 * Return the operator-facing requested-source label.
 *
 * @param scope - Stored preference, or null before admission.
 * @returns Visible label, or null when the run has no stored preference.
 */
export function requestedSearchScopeLabel(
  scope: RequestedSearchScope | null,
): string | null {
  if (scope === null) {
    return null;
  }
  return SEARCH_SCOPE_LABELS[scope];
}
