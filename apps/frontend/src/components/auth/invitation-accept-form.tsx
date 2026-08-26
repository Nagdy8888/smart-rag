/**
 * Authenticated invitation accept. Posts `{ token }` only.
 */

"use client";

import Link from "next/link";
import { useCallback, useState, type FormEvent } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { StatusBanner } from "../ui/status-banner";
import { CodeText, UserText } from "../ui/user-text";
import { acceptInvitation } from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { mutationFailureBanner } from "../../lib/failure-copy";
import { EnvMissingBanner } from "./auth-banners";
import authStyles from "./auth.module.css";

/**
 * Authenticated invitation accept. Posts `{ token }` only.
 *
 * @returns Accept form. Email comes from the signed-in account, not this form.
 */
export function InvitationAcceptForm() {
  const { accessToken, email, supabase } = useSession();
  const [token, setToken] = useState("");
  const [invitationId, setInvitationId] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const onSubmit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      setFailed(null);
      if (accessToken === null) {
        setFailed("Sign in before accepting an invitation.");
        return;
      }
      try {
        const accepted = await acceptInvitation({ accessToken }, token);
        setInvitationId(accepted.invitation_id);
      } catch (error) {
        setFailed(
          error instanceof Error
            ? mutationFailureBanner(error)
            : mutationFailureBanner(new Error("invitation_rejected")),
        );
      }
    },
    [accessToken, token],
  );

  return (
    <div className={authStyles.card}>
      <h1>Accept invitation</h1>
      <p className={authStyles.lead}>
        Email comes from the signed-in account, not this form.
      </p>
      <EnvMissingBanner />
      {accessToken === null ? (
        <StatusBanner kind="warning" role="status">
          Sign in, then paste the invitation token.
        </StatusBanner>
      ) : (
        <p className={authStyles.lead}>
          Signed in as <UserText value={email ?? ""} />.
        </p>
      )}
      {failed ? (
        <StatusBanner kind="error" role="alert">
          {failed}
        </StatusBanner>
      ) : null}
      {invitationId ? (
        <StatusBanner kind="success" role="status">
          Invitation accepted: <CodeText value={invitationId} />
        </StatusBanner>
      ) : null}
      <form className={authStyles.form} onSubmit={(event) => void onSubmit(event)}>
        <Input
          label="Invitation token"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          minLength={8}
          required
        />
        <Button
          type="submit"
          variant="primary"
          disabled={accessToken === null}
          data-action-id="auth.accept_invitation"
          data-testid="auth-accept-invitation"
        >
          Accept invitation
        </Button>
      </form>
      <p className={authStyles.links}>
        <Link href="/login">Sign in</Link>
      </p>
      {supabase === null ? <EnvMissingBanner /> : null}
    </div>
  );
}
