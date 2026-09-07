/**
 * Auth path helpers for Next 16 proxy. Optimistic only.
 */

const PUBLIC_EXACT = new Set([
  "/login",
  "/signup",
  "/forgot-password",
]);

const PUBLIC_PREFIXES = [
  "/auth/callback",
  "/auth/reset",
  "/fonts/",
];

/**
 * Return whether a path may render without a session cookie.
 *
 * @param pathname - Request path.
 * @returns True for Auth-direct routes and self-hosted `/fonts` files.
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

/**
 * Return whether missing public Auth env is treated as signed-out.
 *
 * The Next proxy must not skip login redirects when
 * ``NEXT_PUBLIC_SUPABASE_URL`` or the anon key is unset. FastAPI remains
 * the security boundary.
 *
 * @param url - ``NEXT_PUBLIC_SUPABASE_URL``, possibly empty.
 * @param anonKey - ``NEXT_PUBLIC_SUPABASE_ANON_KEY``, possibly empty.
 * @returns True when both values are non-empty.
 */
export function hasPublicSupabaseConfig(
  url: string | undefined,
  anonKey: string | undefined,
): boolean {
  return Boolean(url && anonKey);
}
