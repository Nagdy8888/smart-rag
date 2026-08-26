/**
 * Public browser environment. Never include privileged secrets.
 */

/**
 * Return the FastAPI origin for authenticated fetch.
 *
 * @returns Origin without a trailing slash. Non-production defaults to
 *   the laptop API. Production fails closed when the public origin is
 *   missing.
 * @throws When `NODE_ENV` is `production` and `NEXT_PUBLIC_API_BASE_URL`
 *   is unset.
 */
export function apiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (raw === undefined || raw === "") {
    if (process.env.NODE_ENV === "production") {
      throw new Error("NEXT_PUBLIC_API_BASE_URL is required in production");
    }
    return "http://127.0.0.1:8000";
  }
  return raw.replace(/\/$/, "");
}

/**
 * Return browser-safe Supabase URL and anon key.
 *
 * @returns Public project URL and anon key, or null when unset outside
 *   production.
 * @throws When `NODE_ENV` is `production` and either public value is
 *   missing.
 */
export function publicSupabaseConfig(): {
  url: string;
  anonKey: string;
} | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    if (process.env.NODE_ENV === "production") {
      throw new Error(
        "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are required in production",
      );
    }
    return null;
  }
  return { url, anonKey };
}
