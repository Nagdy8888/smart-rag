/**
 * Email/password sign-in. Generic failure only.
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { StatusBanner } from "../ui/status-banner";
import { createBrowserSupabase } from "../../lib/auth/browser";
import { CALLBACK_FAILED, SIGN_IN_FAILED } from "../../lib/auth/copy";
import { SIGN_IN_TIMEOUT_MS, raceTimeout } from "../../lib/auth/timeout";
import { EnvMissingBanner, HandshakeBanner } from "./auth-banners";
import authStyles from "./auth.module.css";

export type SignInFormProps = {
  /** True when `/auth/callback` redirected here after a PKCE failure. */
  callbackError?: boolean;
};

/**
 * Email/password sign-in. Generic failure only. FastAPI does not throttle this form.
 *
 * @param props - `callbackError` when `/auth/callback` redirected here.
 * @returns Sign-in card.
 */
export function SignInForm({ callbackError = false }: SignInFormProps) {
  const router = useRouter();
  const supabase = useMemo(() => createBrowserSupabase(), []);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [failed, setFailed] = useState(false);
  const [pending, setPending] = useState(false);

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setFailed(false);
      setPending(true);
      try {
        if (supabase === null) {
          setFailed(true);
          return;
        }
        const result = await raceTimeout(
          supabase.auth.signInWithPassword({ email, password }),
          SIGN_IN_TIMEOUT_MS,
          "sign_in_timeout",
        );
        if (result.error || !result.data.session?.access_token) {
          setFailed(true);
          return;
        }
        router.replace("/");
        router.refresh();
      } catch {
        setFailed(true);
      } finally {
        setPending(false);
      }
    },
    [email, password, router, supabase],
  );

  return (
    <div className={authStyles.card}>
      <h1>Sign in</h1>
      <p className={authStyles.lead}>Access your workspace and knowledge bases.</p>
      <EnvMissingBanner />
      {callbackError ? (
        <StatusBanner kind="error" role="alert">
          {CALLBACK_FAILED}
        </StatusBanner>
      ) : null}
      {failed ? (
        <StatusBanner kind="error" role="alert">
          {SIGN_IN_FAILED}
        </StatusBanner>
      ) : null}
      <HandshakeBanner />
      <form className={authStyles.form} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="Email"
          type="email"
          autoComplete="username"
          placeholder="name@enterprise.com"
          leadingIcon="mail"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          leadingIcon="lock"
          labelEnd={
            <Link className={authStyles.forgot} href="/forgot-password">
              Forgot password
            </Link>
          }
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          revealable
        />
        <Button
          type="submit"
          variant="primary"
          className={authStyles.primaryWide}
          pending={pending}
          pendingLabel="Signing in…"
          data-action-id="auth.sign_in"
          data-testid="auth-sign-in"
        >
          Sign in
        </Button>
      </form>
      <p className={authStyles.links}>
        Don&apos;t have an account? <Link href="/signup">Sign up</Link>
      </p>
    </div>
  );
}
