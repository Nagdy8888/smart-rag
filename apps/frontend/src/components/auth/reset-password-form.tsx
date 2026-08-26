/**
 * Set a new password after a recovery callback.
 */

"use client";

import Link from "next/link";
import { useCallback, useState, type FormEvent } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { StatusBanner } from "../ui/status-banner";
import { SIGN_IN_FAILED } from "../../lib/auth/copy";
import { useSession } from "../../lib/auth/session-provider";
import { EnvMissingBanner } from "./auth-banners";
import authStyles from "./auth.module.css";

/**
 * Set a new password after a recovery callback.
 *
 * @returns Update-password card.
 */
export function ResetPasswordForm() {
  const { supabase } = useSession();
  const [password, setPassword] = useState("");
  const [failed, setFailed] = useState(false);
  const [updated, setUpdated] = useState(false);

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setFailed(false);
      if (supabase === null) {
        setFailed(true);
        return;
      }
      const result = await supabase.auth.updateUser({ password });
      if (result.error) {
        setFailed(true);
        return;
      }
      setUpdated(true);
    },
    [password, supabase],
  );

  return (
    <div className={authStyles.card}>
      <h1>Reset password</h1>
      <EnvMissingBanner />
      {failed ? (
        <StatusBanner kind="error" role="alert">
          {SIGN_IN_FAILED}
        </StatusBanner>
      ) : null}
      {updated ? (
        <StatusBanner kind="success" role="status">
          Password updated. Continue to the console.
        </StatusBanner>
      ) : null}
      <form className={authStyles.form} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="New password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          revealable
        />
        <Button
          type="submit"
          variant="primary"
          className={authStyles.primaryWide}
          data-action-id="auth.reset_password"
          data-testid="auth-reset-password"
        >
          Update password
        </Button>
      </form>
      <p className={authStyles.links}>
        <Link href="/">Console</Link>
      </p>
    </div>
  );
}
