/**
 * Auth path helpers for Next 16 proxy. Optimistic only.
 */

const PUBLIC_EXACT = new Set([
  "/login",
  "/signup",
  "/forgot-password",
  "/review-fixtures",
]);

const PUBLIC_PREFIXES = [
  "/auth/callback",
  "/auth/reset",
  "/mfa/",
  "/unavailable/",
  "/fonts/",
];

/**
 * Return whether a path may render without a session cookie.
 *
 * @param pathname - Request path.
 * @returns True for Auth-direct, Unavailable, and self-hosted `/fonts` files.
 */
export function isPublicAuthPath(pathname: string): boolean {
  if (PUBLIC_EXACT.has(pathname)) {
    return true;
  }
  if (pathname === "/auth/callback" || pathname === "/auth/reset") {
    return true;
  }
  return PUBLIC_PREFIXES.some(
    (prefix) => prefix.endsWith("/") && pathname.startsWith(prefix),
  );
}
