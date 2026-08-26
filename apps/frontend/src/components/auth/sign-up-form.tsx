/**
 * Email/password sign-up. Success is not a dashboard.
 */

"use client";

import Link from "next/link";
import { useCallback, useMemo, useState, type FormEvent } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { StatusBanner } from "../ui/status-banner";
import { UserText } from "../ui/user-text";
import { createBrowserSupabase } from "../../lib/auth/browser";
import { SIGN_IN_FAILED, SIGN_UP_SUCCESS } from "../../lib/auth/copy";
import { EnvMissingBanner } from "./auth-banners";
import authStyles from "./auth.module.css";

/**
 * Email/password sign-up. Success is not a dashboard.
 *
 * @returns Sign-up card.
 */
export function SignUpForm() {
  const supabase = useMemo(() => createBrowserSupabase(), []);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [failed, setFailed] = useState(false);
  const [success, setSuccess] = useState(false);

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setFailed(false);
      if (password !== confirm || supabase === null) {
        setFailed(true);
        return;
      }
      const result = await supabase.auth.signUp({ email, password });
      if (result.error) {
        setFailed(true);
        return;
      }
      setSuccess(true);
    },
    [confirm, email, password, supabase],
  );

  return (
    <div className={authStyles.card}>
      <h1>Sign up</h1>
      <p className={authStyles.lead}>
        Create an account. Workspace access still requires an invitation.
      </p>
      <EnvMissingBanner />
      {failed ? (
        <StatusBanner kind="error" role="alert">
          {SIGN_IN_FAILED}
        </StatusBanner>
      ) : null}
      {success ? (
        <StatusBanner kind="success" role="status">
          {SIGN_UP_SUCCESS}
        </StatusBanner>
      ) : null}
      {success ? (
        <p className={authStyles.lead}>
          Signed up as <UserText value={email} />.
        </p>
      ) : null}
      <form className={authStyles.form} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="Email"
          type="email"
          autoComplete="username"
          leadingIcon="mail"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <Input
          label="Password"
          type="password"
          autoComplete="new-password"
          leadingIcon="lock"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          revealable
        />
        <Input
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          leadingIcon="lock"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          required
          revealable
        />
        <Button
          type="submit"
          variant="primary"
          className={authStyles.primaryWide}
          data-action-id="auth.sign_up"
          data-testid="auth-sign-up"
        >
          Sign up
        </Button>
      </form>
      <p className={authStyles.links}>
        Already have an account? <Link href="/login">Sign in</Link>
      </p>
    </div>
  );
}
