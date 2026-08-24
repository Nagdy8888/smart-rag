/**
 * Next.js 16 proxy: refresh Supabase Auth cookies before rendering.
 *
 * Optimistic redirects are convenience only. FastAPI still authorizes every
 * Bearer call. Missing cookies are not the security boundary.
 *
 * Do not add `middleware.ts` beside this file.
 */

import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";
import { isPublicAuthPath } from "./lib/auth/paths";
import { AUTH_CLAIMS_TIMEOUT_MS, raceTimeout } from "./lib/auth/timeout";

/**
 * Copy refreshed Auth cookies onto a redirect so PKCE/session is not dropped.
 *
 * @param from - Response that received `setAll`.
 * @param to - Redirect response.
 * @returns `to` with cookies copied.
 */
function copyCookies(from: NextResponse, to: NextResponse): NextResponse {
  from.cookies.getAll().forEach((cookie) => {
    to.cookies.set(cookie);
  });
  return to;
}

/**
 * Refresh the Auth session and optionally redirect unauthenticated `/`.
 *
 * @param request - Incoming Next request.
 * @returns Next response with updated cookies.
 */
export async function proxy(request: NextRequest): Promise<NextResponse> {
  let supabaseResponse = NextResponse.next({ request });
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    return supabaseResponse;
  }

  const supabase = createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });
        supabaseResponse = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => {
          supabaseResponse.cookies.set(name, value, options);
        });
      },
    },
  });

  let signedIn = false;
  try {
    const { data } = await raceTimeout(
      supabase.auth.getClaims(),
      AUTH_CLAIMS_TIMEOUT_MS,
      "auth_claims_timeout",
    );
    signedIn = Boolean(data?.claims);
  } catch {
    signedIn = false;
  }
  const { pathname } = request.nextUrl;

  if (!signedIn && !isPublicAuthPath(pathname)) {
    const login = request.nextUrl.clone();
    login.pathname = "/login";
    if (pathname !== "/") {
      login.searchParams.set("next", pathname);
    }
    return copyCookies(supabaseResponse, NextResponse.redirect(login));
  }

  if (
    signedIn &&
    (pathname === "/login" || pathname === "/signup" || pathname === "/forgot-password")
  ) {
    const home = request.nextUrl.clone();
    home.pathname = "/";
    home.search = "";
    return copyCookies(supabaseResponse, NextResponse.redirect(home));
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|fonts/|.*\\.(?:svg|png|jpg|jpeg|gif|webp|woff2|woff)$).*)",
  ],
};
