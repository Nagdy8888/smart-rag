/**
 * Sanitized FastAPI failure banners. Codes only; never stack traces.
 */

import type { ApiFailure } from "./api";
import { MFA_REQUIRED_BANNER, SESSION_REVOKED_BANNER } from "./auth/copy";
import { handshakeBelowMinCopy } from "./handshake";
import { displayText } from "./safe-text";

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
    case "mfa":
      return MFA_REQUIRED_BANNER;
    case "auth":
      if (failure.detail === "session_revoked") {
        return SESSION_REVOKED_BANNER;
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
    case "deleted":
      return "Conversation deleted. Reads, resume, and citations are denied. No source text is shown.";
    default: {
      const _exhaustive: never = failure;
      return String(_exhaustive);
    }
  }
}
