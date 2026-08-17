/**
 * Honest client-navigation contract. Hidden chrome is not authorization.
 *
 * There is no `isServerAuthorized` helper in this package. FastAPI and
 * RLS remain the only permission boundary. Omitting a nav item must not
 * be treated as HTTP 403.
 */

/**
 * Constant documenting that AppShell visibility is convenience only.
 *
 * @returns Always `true` so tests can assert the contract exists.
 */
export const CLIENT_NAV_IS_NOT_AUTHORIZATION = true as const;

/**
 * Return whether omitting a client nav item implies a server 403.
 *
 * @param _path - Path that might be hidden from the shell. Ignored.
 * @returns Always `false`. Callers must still hit the real API.
 * @remarks
 * Side effects: none. This function does not fetch, cache, or gate
 * requests. Packet 2+ clients must keep calling FastAPI even when the
 * matching control is absent.
 */
export function hiddenNavImpliesForbidden(path: string): false {
  void path;
  return false;
}

/**
 * Return whether a UI control may be used as the authorization boundary.
 *
 * @returns Always `false`.
 */
export function clientControlIsAuthorizationBoundary(): false {
  return false;
}

/**
 * Return whether a forged client `role=owner` claim authorizes FastAPI.
 *
 * @returns Always `false`. Requests use Bearer only; no role header.
 */
export function forgedClientRoleIsAuthorization(): false {
  return false;
}
