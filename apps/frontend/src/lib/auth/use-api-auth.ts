/**
 * Memoized FastAPI Bearer wrapper derived from the browser session.
 */

"use client";

import { useMemo } from "react";
import type { ApiAuth } from "../api";
import { useSession } from "./session-provider";

/**
 * Return `{ accessToken }` for FastAPI, or null when signed out.
 *
 * Does not create a Supabase client or refresh tokens. The object identity
 * is stable while the token string is unchanged.
 *
 * @returns Auth header owner, or null.
 */
export function useApiAuth(): ApiAuth | null {
  const { accessToken } = useSession();
  return useMemo(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
}
