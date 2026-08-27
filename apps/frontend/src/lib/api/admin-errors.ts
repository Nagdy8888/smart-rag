/**
 * Administration error mapping. 404 is not conversation deletion.
 */

import { classifyApiError, sanitizedDetail } from "./errors";

/**
 * Map a non-OK administration response to a thrown Error code.
 *
 * 404 is not treated as conversation deletion. 403 is authorization, not MFA.
 *
 * @param status - HTTP status.
 * @param body - JSON-ish object.
 * @param headers - Optional headers for 429 Retry-After classification.
 * @throws Error with `forbidden`, `budget_exhausted`,
 *   `rate_limited`, `stale_row_version`, or a sanitized detail.
 */
export function throwClassifiedAdminError(
  status: number,
  body: Record<string, unknown>,
  headers?: Headers | Record<string, string>,
): never {
  const classified = classifyApiError(status, body, headers);
  if (classified?.kind === "budget") {
    throw new Error("budget_exhausted");
  }
  if (classified?.kind === "rate") {
    throw new Error("rate_limited");
  }
  if (classified?.kind === "auth") {
    const detail = classified.detail;
    if (detail === "forbidden" || detail === "authorization_rejected") {
      throw new Error("forbidden");
    }
    throw new Error("request_rejected");
  }
  if (classified?.kind === "server") {
    throw new Error("request_rejected");
  }
  if (classified?.kind === "validation") {
    throw new Error(classified.detail);
  }
  if (status === 409) {
    throw new Error(sanitizedDetail(body, "stale_row_version"));
  }
  if (status === 400) {
    throw new Error(sanitizedDetail(body, "request_rejected"));
  }
  throw new Error("request_rejected");
}
