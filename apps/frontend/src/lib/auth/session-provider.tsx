/**
 * Browser session context. Access tokens come from `@supabase/ssr` cookies
 * via `getSession` / `onAuthStateChange`, not from a one-shot `useState`
 * after password sign-in.
 */

"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { createBrowserSupabase } from "./browser";
import { SESSION_RESTORE_TIMEOUT_MS, raceTimeout } from "./timeout";

export type SessionSnapshot = {
  /** Bearer JWT for FastAPI, or null when signed out. */
  accessToken: string | null;
  /** JWT email for invitation-accept copy. Not sent as a FastAPI body field. */
  email: string | null;
  /** False until the first `getSession` settles. */
  ready: boolean;
  /** Browser client, or null when public env is missing. */
  supabase: ReturnType<typeof createBrowserSupabase>;
  /**
   * Sign out of Auth. FastAPI then rejects the previous Bearer.
   *
   * @returns Promise that settles after Auth sign-out.
   */
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionSnapshot | null>(null);

/**
 * Provide the current Auth session to client trees.
 *
 * @param props - App Router children.
 * @returns Context provider.
 * @remarks
 * Side effects: subscribes to `onAuthStateChange`. `getSession` is bounded
 * by `SESSION_RESTORE_TIMEOUT_MS` so a hung Auth call cannot freeze Chat
 * on "Restoring session." Missing cookies are not the security boundary;
 * FastAPI still authorizes Bearer calls.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const supabase = useMemo(() => createBrowserSupabase(), []);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(supabase === null);

  useEffect(() => {
    if (supabase === null) {
      return;
    }
    let cancelled = false;
    void raceTimeout(
      supabase.auth.getSession(),
      SESSION_RESTORE_TIMEOUT_MS,
      "session_restore_timeout",
    )
      .then(({ data }) => {
        if (cancelled) {
          return;
        }
        setAccessToken(data.session?.access_token ?? null);
        setEmail(data.session?.user.email ?? null);
      })
      .catch(() => {
        /* Stay signed out in the snapshot so the console unfreezes. */
      })
      .finally(() => {
        if (!cancelled) {
          setReady(true);
        }
      });
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setAccessToken(session?.access_token ?? null);
      setEmail(session?.user.email ?? null);
    });
    return () => {
      cancelled = true;
      data.subscription.unsubscribe();
    };
  }, [supabase]);

  const signOut = useCallback(async () => {
    await supabase?.auth.signOut();
    setAccessToken(null);
    setEmail(null);
  }, [supabase]);

  const value = useMemo<SessionSnapshot>(
    () => ({ accessToken, email, ready, supabase, signOut }),
    [accessToken, email, ready, supabase, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/**
 * Read the Auth session from context.
 *
 * @returns Session snapshot.
 * @throws Error when used outside `SessionProvider`.
 */
export function useSession(): SessionSnapshot {
  const value = useContext(SessionContext);
  if (value === null) {
    throw new Error("useSession requires SessionProvider");
  }
  return value;
}
