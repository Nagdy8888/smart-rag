/**
 * Request a password-reset email. Always shows check-inbox copy after submit.
 */

"use client";

import Link from "next/link";
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { StatusBanner } from "../ui/status-banner";
import { createBrowserSupabase } from "../../lib/auth/browser";
import { RESET_EMAIL_SENT } from "../../lib/auth/copy";
import { EnvMissingBanner } from "./auth-banners";
import authStyles from "./auth.module.css";

/**
 * Request a password-reset email. Always shows check-inbox copy after submit.
 *
 * @returns Forgot-password card. PKCE recovery returns through `/auth/callback`.
 */
export function ForgotPasswordForm() {
  const supabase = useMemo(() => createBrowserSupabase(), []);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      if (supabase !== null) {
        const origin = window.location.origin;
        await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${origin}/auth/callback?next=/auth/reset`,
        });
      }
      setSent(true);
    },
    [email, supabase],
  );

  return (
    <div className={authStyles.card}>
      <h1>Forgot password</h1>
      <p className={authStyles.lead}>
        We will send a reset link if that address can receive mail.
      </p>
      <EnvMissingBanner />
      {sent ? (
        <StatusBanner kind="info" role="status">
          {RESET_EMAIL_SENT}
        </StatusBanner>
      ) : null}
      <form className={authStyles.form} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="Email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <Button
          type="submit"
          variant="primary"
          className={authStyles.primaryWide}
          data-action-id="auth.forgot_password"
          data-testid="auth-forgot-password"
        >
          Send reset link
        </Button>
      </form>
      <p className={authStyles.links}>
        <Link href="/login">Sign in</Link>
      </p>
    </div>
  );
}
