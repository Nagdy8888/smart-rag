/**
 * Public browser environment. Never include privileged secrets.
 */

/**
 * Return the FastAPI origin for authenticated fetch.
 *
 * @returns Origin without a trailing slash. Defaults to local API.
 */
export function apiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
  return raw.replace(/\/$/, "");
}

/**
 * Return browser-safe Supabase URL and anon key.
 *
 * @returns Public project URL and anon key, or null when unset.
 */
export function publicSupabaseConfig(): {
  url: string;
  anonKey: string;
} | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    return null;
  }
  return { url, anonKey };
}
