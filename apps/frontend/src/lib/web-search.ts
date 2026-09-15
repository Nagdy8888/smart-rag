/**
 * Ask Web-mode capability helpers. Hidden chrome is not authorization.
 */

import {
  REQUESTED_SEARCH_SCOPES,
  type RequestedSearchScope,
} from "./types/chat";

/**
 * Return whether `/api/meta` advertises Web search.
 *
 * @param meta - Handshake body, or null while loading.
 * @returns True only when the server flag is explicitly true.
 */
export function webSearchCapability(
  meta: { web_search_enabled?: boolean } | null | undefined,
): boolean {
  return meta?.web_search_enabled === true;
}

/**
 * Clamp a stored preference when Web is not advertised.
 *
 * @param scope - Session or resume preference.
 * @param webSearchEnabled - `/api/meta` flag.
 * @returns `auto` when `web` is stored but the option is hidden.
 */
export function visibleRequestedSearchScope(
  scope: RequestedSearchScope,
  webSearchEnabled: boolean,
): RequestedSearchScope {
  if (scope === "web" && !webSearchEnabled) {
    return "auto";
  }
  return scope;
}

/**
 * Return Ask dropdown values in catalog order.
 *
 * @param webSearchEnabled - `/api/meta` flag.
 * @returns Auto, Company documents, General, and Web only when enabled.
 */
export function visibleSearchScopes(
  webSearchEnabled: boolean,
): readonly RequestedSearchScope[] {
  if (webSearchEnabled) {
    return REQUESTED_SEARCH_SCOPES;
  }
  return REQUESTED_SEARCH_SCOPES.filter((scope) => scope !== "web");
}
