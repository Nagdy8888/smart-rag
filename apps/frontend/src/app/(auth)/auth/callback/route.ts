/**
 * PKCE callback. Exchanges `code` then redirects. Replay of a consumed code
 * shows generic failure copy on `/login`.
 */

import { NextResponse } from "next/server";
import { createServerSupabase } from "../../../../lib/auth/server";

/**
 * Allow only same-origin relative next paths.
 *
 * @param raw - `next` query value.
 * @returns Safe path starting with `/`.
 */
function safeNextPath(raw: string | null): string {
  if (raw === null || raw === "") {
    return "/";
  }
  if (!raw.startsWith("/") || raw.startsWith("//")) {
    return "/";
  }
  return raw;
}

/**
 * Exchange the Auth `code` for a session cookie.
 *
 * @param request - Callback GET with `code` and optional `next`.
 * @returns Redirect to `next` or `/login?error=callback`.
 * @remarks
 * Side effects: writes Auth cookies via `exchangeCodeForSession`. Uses the
 * anon key only.
 */
export async function GET(request: Request): Promise<NextResponse> {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const next = safeNextPath(url.searchParams.get("next"));
  const fail = NextResponse.redirect(new URL("/login?error=callback", url.origin));
  if (!code) {
    return fail;
  }
  const supabase = await createServerSupabase();
  if (supabase === null) {
    return fail;
  }
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    return fail;
  }
  return NextResponse.redirect(new URL(next, url.origin));
}
