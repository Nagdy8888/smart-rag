/**
 * Paid, resume, and admin request headers. No fetch calls.
 */

import { CLIENT_VERSION } from "../client-version";
import type { RequestedSearchScope } from "../types";

/** Headers shared by paid POST bodies. Resume GET omits the version. */
export type ApiAuth = {
  accessToken: string;
};

/**
 * Build JSON headers for a new paid mutation.
 *
 * @param auth - Bearer token.
 * @param idempotencyKey - Optional UUID reused across retry.
 * @returns Header map including `X-Client-Version`.
 */
export function paidMutationHeaders(
  auth: ApiAuth,
  idempotencyKey?: string,
): Record<string, string> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${auth.accessToken}`,
    "Content-Type": "application/json",
    "X-Client-Version": CLIENT_VERSION,
  };
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }
  return headers;
}

/**
 * JSON body for `POST /conversations/{id}/messages`. Auto Composite envelope.
 * There is no client route field (GAP-07-01). `search_scope` is a source
 * preference only.
 *
 * @param message - Untrusted user text.
 * @param idempotencyKey - Stable UUID.
 * @param searchScope - Client source preference captured for this key.
 * @returns `{ message, idempotency_key, search_scope }` only.
 */
export function submitMessageBody(
  message: string,
  idempotencyKey: string,
  searchScope: RequestedSearchScope,
): {
  message: string;
  idempotency_key: string;
  search_scope: RequestedSearchScope;
} {
  return {
    message,
    idempotency_key: idempotencyKey,
    search_scope: searchScope,
  };
}

/**
 * Build headers for resume/cancel/read paths. No version handshake.
 *
 * @param auth - Bearer token.
 * @param lastEventId - Optional Last-Event-ID for SSE resume.
 * @returns Header map.
 */
export function resumeHeaders(
  auth: ApiAuth,
  lastEventId?: string,
): Record<string, string> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${auth.accessToken}`,
  };
  if (lastEventId) {
    headers["Last-Event-ID"] = lastEventId;
  }
  return headers;
}

/**
 * JSON headers for AUTH_ADJACENT administration POSTs.
 *
 * Handshake `X-Client-Version` is reserved for paid chat/upload. These
 * mutations send Bearer only. Production never sends `X-Test-*`.
 *
 * @param auth - Access token.
 * @returns Header map.
 */
export function adminMutationHeaders(auth: ApiAuth): Record<string, string> {
  return {
    ...resumeHeaders(auth),
    "Content-Type": "application/json",
  };
}
