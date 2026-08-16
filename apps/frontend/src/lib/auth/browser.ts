/**
 * Browser Supabase client. Uses the public anon key only.
 */

"use client";

import { createBrowserClient } from "@supabase/ssr";
import { publicSupabaseConfig } from "../env";

/**
 * Create a browser Supabase client for password sign-in.
 *
 * @returns Client, or null when public env is missing.
 */
export function createBrowserSupabase() {
  const config = publicSupabaseConfig();
  if (config === null) {
    return null;
  }
  return createBrowserClient(config.url, config.anonKey);
}
