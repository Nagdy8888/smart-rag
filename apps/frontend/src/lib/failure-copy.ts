/**
 * Sanitized FastAPI failure banners. Codes only; never stack traces.
 */

import {
  FORBIDDEN_MUTATION_COPY,
  STALE_ROW_VERSION_COPY,
} from "./admin-copy";
import type { ApiFailure } from "./api";
import { SESSION_REVOKED_BANNER } from "./auth/copy";
import { handshakeBelowMinCopy } from "./handshake";
import { INSUFFICIENT_EVIDENCE_COPY } from "./limitations";
import { displayText } from "./safe-text";

export { INSUFFICIENT_EVIDENCE_COPY };

/** Unknown 5xx and unclassified failures. Never exception text. */
export const GENERIC_PRODUCTION_ERROR = "Something went wrong.";

/** Forced Web when `WEB_SEARCH_ENABLED` is false. Not a limiter outage. */
export const WEB_SEARCH_DISABLED_COPY =
  "Web search is not enabled. Forced Web was refused with no reservation.";

/** Forced Web when Exa is missing. Not a limiter outage. */
export const WEB_SEARCH_UNCONFIGURED_COPY =
  "Web search is not configured. Forced Web was refused with no reservation.";

/**
 * Map a classified API failure to English chrome.
 *
 * @param failure - Typed gate.
 * @returns Banner body. Uses `detail` codes from the contract.
 */
export function apiFailureBanner(failure: ApiFailure): string {
  switch (failure.kind) {
    case "upgrade":
      return handshakeBelowMinCopy();
    case "auth":
      if (failure.detail === "session_revoked") {
        return SESSION_REVOKED_BANNER;
      }
      if (failure.status === 403) {
        return FORBIDDEN_MUTATION_COPY;
      }
      return `Session rejected (${displayText(failure.detail)}). Sign in again. UI state is not authorization.`;
    case "budget":
      return `Budget exhausted (${displayText(failure.detail)}).`;
    case "rate": {
      const retry =
        failure.retryAfter !== null && failure.retryAfter !== ""
          ? ` Retry-After ${displayText(failure.retryAfter)}.`
          : "";
      return `Request limited (${displayText(failure.detail)}).${retry}`;
    }
    case "fail_closed":
      return `Limiter fail-closed (${displayText(failure.detail)}). Approved reads may degrade; cost mutations are denied.`;
    case "unavailable":
      if (failure.detail === "web_search_disabled") {
        return WEB_SEARCH_DISABLED_COPY;
      }
      if (failure.detail === "web_search_unconfigured") {
        return WEB_SEARCH_UNCONFIGURED_COPY;
      }
      return `Service unavailable (${displayText(failure.detail)}).`;
    case "deleted":
      return "Conversation deleted. Reads, resume, and citations are denied. No source text is shown.";
    case "conflict":
      return `Request conflict (${displayText(failure.detail)}). Reload and retry.`;
    case "validation":
      return `Request invalid (${displayText(failure.detail)}).`;
    case "protocol":
      if (failure.detail === "empty_answer") {
        return "The run completed without an answer.";
      }
      if (failure.detail === "run_failed") {
        return GENERIC_PRODUCTION_ERROR;
      }
      if (
        failure.detail === "insufficient_evidence" ||
        failure.detail === "refused"
      ) {
        return INSUFFICIENT_EVIDENCE_COPY;
      }
      return `Run error (${displayText(failure.detail)}).`;
    case "server":
      return GENERIC_PRODUCTION_ERROR;
    default: {
      const _exhaustive: never = failure;
      return String(_exhaustive);
    }
  }
}

/**
 * Map a thrown administration helper error to English chrome.
 *
 * @param error - `Error` from create/offboard/enable/curation/usage helpers.
 * @returns Banner body. Codes only; never stack traces.
 */
export function mutationFailureBanner(error: Error): string {
  switch (error.message) {
    case "forbidden":
      return FORBIDDEN_MUTATION_COPY;
    case "budget_exhausted":
      return apiFailureBanner({ kind: "budget", detail: "budget_exhausted" });
    case "rate_limited":
      return apiFailureBanner({
        kind: "rate",
        detail: "rate_limited",
        retryAfter: null,
      });
    case "stale_row_version":
      return STALE_ROW_VERSION_COPY;
    default:
      if (/^[a-z][a-z0-9_]{0,63}$/i.test(error.message)) {
        return apiFailureBanner({ kind: "validation", detail: error.message });
      }
      return GENERIC_PRODUCTION_ERROR;
  }
}

/**
 * Render one chat-run alert. The run ID appears at most once as a support
 * reference. Internal status codes such as `run_failed` stay out of chrome.
 *
 * @param failure - Classified chat failure.
 * @param runId - Durable run identifier, or null.
 * @returns Single banner body.
 */
export function chatRunFailureBanner(
  failure: ApiFailure,
  runId: string | null,
): string {
  const body = apiFailureBanner(failure);
  if (runId === null || runId === "") {
    return body;
  }
  return `${body} Reference ${runId}.`;
}

/**
 * Return signed copy for an expected graceful Ask outcome.
 *
 * @param terminal - Catalog terminal, or null while the run is live.
 * @param status - Partial reason or node status.
 * @param limitationCodes - SSE limitation codes in arrival order.
 * @returns Refusal copy, or null when the outcome is not an expected
 *   company-evidence refusal.
 */
export function expectedRefusalCopy(
  terminal: string | null,
  status: string | null | undefined,
  limitationCodes: readonly string[],
): string | null {
  if (terminal !== null && terminal !== "partial") {
    return null;
  }
  if (
    limitationCodes.includes("insufficient_evidence") ||
    status === "insufficient_evidence" ||
    status === "refused"
  ) {
    return INSUFFICIENT_EVIDENCE_COPY;
  }
  return null;
}
