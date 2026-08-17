/**
 * Server Supabase client. Anon key only. PKCE is forced by `@supabase/ssr`
 * 0.7.0 `createServerClient`.
 */

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { publicSupabaseConfig } from "../env";

/**
 * Create a cookie-backed server client for Route Handlers and Server Components.
 *
 * @returns Client, or null when public env is missing.
 * @remarks
 * `setAll` may throw in Server Components; `src/proxy.ts` refreshes cookies.
 * Never pass a service-role key.
 */
export async function createServerSupabase() {
  const config = publicSupabaseConfig();
  if (config === null) {
    return null;
  }
  const cookieStore = await cookies();
  return createServerClient(config.url, config.anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // Proxy owns refresh when this runs in a Server Component.
        }
      },
    },
  });
}
