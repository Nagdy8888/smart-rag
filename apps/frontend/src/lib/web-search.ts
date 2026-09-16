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
 * Return a stored Answer-source preference for the dropdown.
 *
 * Web stays selectable even when `/api/meta` `web_search_enabled` is
 * false. Hidden chrome is not authorization; admit still refuses Web
 * when the server flag is off.
 *
 * @param scope - Session or resume preference.
 * @param webSearchEnabled - Server capability. Unused; hidden chrome is not
 *   authorization.
 * @returns The same catalog value.
 */
export function visibleRequestedSearchScope(
  scope: RequestedSearchScope,
  webSearchEnabled: boolean,
): RequestedSearchScope {
  void webSearchEnabled;
  return scope;
}

/**
 * Return Ask dropdown values in catalog order.
 *
 * @param webSearchEnabled - Server capability. Unused; Web stays listed.
 * @returns Auto, Company documents, General, and Web.
 */
export function visibleSearchScopes(
  webSearchEnabled: boolean,
): readonly RequestedSearchScope[] {
  void webSearchEnabled;
  return REQUESTED_SEARCH_SCOPES;
}
