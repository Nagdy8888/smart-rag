/**
 * User-facing labels for Ask run details. Catalog keys stay in state;
 * this module never invents a route, terminal, or correction.
 */

import type { StatusTone } from "../components/ui/status-pill";
import type { IconName } from "../components/ui/icon";
import { displayText } from "./safe-text";

const ROUTE_LABELS: Readonly<Record<string, string>> = {
  hybrid: "Hybrid",
  combined: "Combined",
  composite: "Composite",
  structured_table: "Tables",
  graph_inspection: "Graph inspection",
  web_research: "Web research",
  no_retrieval: "No document search",
  NoRetrieval: "No document search",
};

const ROUTE_SUMMARIES: Readonly<Record<string, string>> = {
  hybrid: "Searches authorized documents.",
  combined: "Searches documents and relationships.",
  composite: "Searches documents, tables, and relationships.",
  structured_table: "Reads authorized spreadsheet and table values.",
  graph_inspection: "Inspects the graph only. This is not an answering mode.",
  web_research: "Searches the public web. Does not search company documents.",
  no_retrieval: "Did not search company documents.",
  NoRetrieval: "Did not search company documents.",
};

const TERMINAL_LABELS: Readonly<Record<string, string>> = {
  completed: "Completed",
  partial: "Partial",
  cancelled: "Cancelled",
  error: "Error",
  deadline: "Deadline reached",
};

/**
 * Answer-column copy when Composite (or any family) exhausted the run
 * deadline before verified tokens. Catalog terminal is still `partial`.
 */
export const EMPTY_DEADLINE_PARTIAL_COPY =
  "This run reached its time limit before an answer was ready. Send the question again.";

/**
 * Return whether a chat-view status is a retrieve-time deadline partial.
 *
 * @param status - SSE `partial.reason` stored on the view, or null.
 * @returns True for retrieve-time `deadline_exhausted`, the answer-stage
 *   reserve reason, and the shorter `deadline` alias.
 */
export function isDeadlinePartialStatus(status: string | null | undefined): boolean {
  return (
    status === "deadline_exhausted" ||
    status === "deadline" ||
    status === "answer_deadline_reserve_exhausted"
  );
}

const CORRECTION_REASONS: Readonly<Record<string, string>> = {
  relationship: "The question needed relationship search.",
};

const CACHE_LABELS: Readonly<Record<string, string>> = {
  hit: "Reused a cached search",
  cache_hit: "Reused a cached search",
  miss: "Fresh search",
  cache_miss: "Fresh search",
};

/**
 * Return whether a diagnostic string is real enough to render.
 *
 * @param value - Candidate label or catalog value.
 * @returns False for null, empty, dash, and the placeholder `none`.
 */
export function isRealDetailValue(
  value: string | null | undefined,
): value is string {
  if (value === null || value === undefined) {
    return false;
  }
  const trimmed = value.trim();
  return trimmed !== "" && trimmed !== "—" && trimmed.toLowerCase() !== "none";
}

/**
 * Return the operator-facing search-mode label.
 *
 * Unknown catalog values stay isolated text and are never treated as HTML.
 *
 * @param route - Server `route_family` or correction target.
 * @returns Visible label, or null when the value is empty.
 */
export function routeLabel(route: string | null | undefined): string | null {
  if (!isRealDetailValue(route)) {
    return null;
  }
  return ROUTE_LABELS[route] ?? displayText(route);
}

/**
 * Return one sentence explaining a known search mode.
 *
 * @param route - Server `route_family`.
 * @returns Signed summary, or null when the family is unknown or empty.
 */
export function routeSummary(route: string | null | undefined): string | null {
  if (!isRealDetailValue(route)) {
    return null;
  }
  return ROUTE_SUMMARIES[route] ?? null;
}

/**
 * Return the run-status label for the details sheet.
 *
 * Never returns `running` when `runId` is null.
 *
 * @param terminal - Catalog terminal, or null while the stream is open.
 * @param runId - Current run id, or null before admission.
 * @returns Visible status, or null when there is no run.
 */
export function runStatusLabel(
  terminal: string | null,
  runId: string | null,
): string | null {
  if (terminal !== null && TERMINAL_LABELS[terminal]) {
    return TERMINAL_LABELS[terminal];
  }
  if (terminal !== null && isRealDetailValue(terminal)) {
    return displayText(terminal);
  }
  if (runId !== null) {
    return "In progress";
  }
  return null;
}

/**
 * Return operator-facing copy for a route-correction reason.
 *
 * @param reason - SSE `route_correction.reason`.
 * @returns Signed sentence, or isolated text for an unknown reason.
 */
export function correctionReasonLabel(
  reason: string | null | undefined,
): string | null {
  if (!isRealDetailValue(reason)) {
    return null;
  }
  return CORRECTION_REASONS[reason] ?? displayText(reason);
}

/**
 * Return the StatusPill tone for a run-details status.
 *
 * @param terminal - Catalog terminal, or null while the stream is open.
 * @param runId - Current run id, or null before admission.
 * @returns Tone. Idle stays neutral.
 */
export function runStatusTone(
  terminal: string | null,
  runId: string | null,
): StatusTone {
  if (terminal === "completed") {
    return "success";
  }
  if (terminal === "error") {
    return "danger";
  }
  if (terminal === "partial" || terminal === "deadline") {
    return "warning";
  }
  if (runId !== null && terminal === null) {
    return "neutral";
  }
  return "neutral";
}

/**
 * Return one supporting sentence for the status card.
 *
 * @param terminal - Catalog terminal, or null while the stream is open.
 * @param verified - True after `verify_answer` completed.
 * @returns Sentence, or null when there is no run status.
 */
export function runStatusSummary(
  terminal: string | null,
  verified: boolean,
): string | null {
  if (terminal === "completed") {
    return verified ? "Verified and ready." : "The run finished.";
  }
  if (terminal === "partial") {
    return "Some verified text was kept.";
  }
  if (terminal === "cancelled") {
    return "This run was stopped.";
  }
  if (terminal === "error") {
    return "This run did not finish.";
  }
  if (terminal === "deadline") {
    return "The time limit was reached.";
  }
  if (terminal === null) {
    return "Working on this question.";
  }
  return null;
}

/**
 * Return the icon for a known search mode.
 *
 * Unknown routes use the search icon.
 *
 * @param route - Server `route_family`.
 * @returns Typed icon name.
 */
export function routeIcon(route: string | null | undefined): IconName {
  if (route === "structured_table") {
    return "tables";
  }
  if (route === "graph_inspection") {
    return "graph";
  }
  if (route === "hybrid" || route === "combined" || route === "composite" || route === "web_research") {
    return "search";
  }
  return "search";
}

export type SearchModeChatSlice = {
  requestedSearchScope: string | null;
  answerOrigin: string | null;
  routeFamily: string | null;
  diagnostics: { effectiveRoute: string | null };
};

/**
 * Return the user-facing search-mode catalog key for Run details.
 *
 * Composite is the Auto envelope, not the operator-facing source. General
 * and Web answers must not inherit “Searches documents…” copy from that
 * envelope.
 *
 * @param chat - Scope, origin, and envelope diagnostics for the current run.
 * @returns Catalog route key, or null when nothing real is present.
 */
export function searchModeRoute(chat: SearchModeChatSlice): string | null {
  const origin = chat.answerOrigin;
  const scope = chat.requestedSearchScope;
  if (
    origin === "general_knowledge" ||
    scope === "general_knowledge" ||
    origin === "user_supplied_text" ||
    scope === "user_supplied_text" ||
    origin === "ambiguous" ||
    origin === "deterministic"
  ) {
    return "no_retrieval";
  }
  if (origin === "web" || scope === "web") {
    return "web_research";
  }
  return chat.diagnostics.effectiveRoute ?? chat.routeFamily;
}

/**
 * Return operator-facing copy for a cache diagnostic.
 *
 * @param status - SSE `cache.status`.
 * @returns Signed sentence, or isolated text for an unknown status.
 */
export function cacheStatusLabel(
  status: string | null | undefined,
): string | null {
  if (!isRealDetailValue(status)) {
    return null;
  }
  return CACHE_LABELS[status] ?? displayText(status);
}
