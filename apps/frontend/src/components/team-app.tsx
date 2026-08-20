/**
 * Team invitations and offboarding. No member directory HTTP.
 */

"use client";

import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { HandshakeBanner } from "./auth/auth-screens";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { LimitationCallout } from "./ui/limitation-callout";
import { StatusBanner } from "./ui/status-banner";
import { CodeText, UserText } from "./ui/user-text";
import {
  createInvitation,
  fetchMe,
  offboardUser,
  type ApiAuth,
} from "../lib/api";
import {
  INVITE_TOKEN_MAIL_ONLY,
  NO_MEMBER_DIRECTORY_COPY,
  OFFBOARD_IRREVERSIBLE_COPY,
  TEAM_OWNER_BOOTSTRAP_UNAVAILABLE,
} from "../lib/admin-copy";
import { useSession } from "../lib/auth/session-provider";
import { mutationFailureBanner } from "../lib/failure-copy";
import { sessionQueryKeys } from "../lib/query-keys";
import { showInviteConvenience, showOffboardConvenience } from "../lib/roles";
import {
  INVITE_ROLES,
  type CreateInvitationResponse,
  type InviteRole,
  type OffboardResponse,
} from "../lib/types";
import styles from "./developer-app.module.css";

/**
 * Team surface: invite create, offboard by user_id, accept link.
 *
 * @returns Team administration panel.
 * @remarks
 * Convenience hiding is not authorization. `createInvitation` and
 * `offboardUser` still exist for forged-role tests.
 */
export function TeamApp() {
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InviteRole>("member");
  const [uploadEnabled, setUploadEnabled] = useState(false);
  const [subjectUserId, setSubjectUserId] = useState("");
  const [created, setCreated] = useState<CreateInvitationResponse | null>(null);
  const [offboarded, setOffboarded] = useState<OffboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const meQuery = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });
  const canInvite = showInviteConvenience(meQuery.data?.role);
  const canOffboard = showOffboardConvenience(meQuery.data?.role);

  const inviteMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return createInvitation(auth, {
        email,
        role,
        upload_enabled: role === "viewer" ? false : uploadEnabled,
      });
    },
    onSuccess: (result) => {
      setCreated(result);
      setOffboarded(null);
      setError(null);
    },
    onError: (caught: Error) => {
      setCreated(null);
      setError(mutationFailureBanner(caught));
    },
  });

  const offboardMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return offboardUser(auth, subjectUserId.trim());
    },
    onSuccess: (result) => {
      setOffboarded(result);
      setCreated(null);
      setError(null);
    },
    onError: (caught: Error) => {
      setOffboarded(null);
      setError(mutationFailureBanner(caught));
    },
  });

  return (
    <div className={styles.shell}>
      <header className={styles.pageHeader}>
        <div>
          <h1>Team</h1>
          <p className={styles.pageLead}>
            Invite people and offboard accounts. There is no member directory.
          </p>
        </div>
      </header>
      <HandshakeBanner />
      {error ? (
        <StatusBanner kind="error" role="alert">
          {error}
        </StatusBanner>
      ) : null}
      <LimitationCallout tone="neutral">{NO_MEMBER_DIRECTORY_COPY}</LimitationCallout>
      <LimitationCallout tone="warning">
        {TEAM_OWNER_BOOTSTRAP_UNAVAILABLE}
      </LimitationCallout>
      <p className={styles.muted}>
        Invitation accept is already implemented.{" "}
        <Link href="/invitations/accept">Accept an invitation</Link>.
      </p>

      {canInvite ? (
        <section className={styles.panel} data-testid="invite-form" aria-label="Invite">
          <h2>Create invitation</h2>
          <div className={styles.formGrid}>
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <label>
              Role
              <select
                value={role}
                onChange={(event) => setRole(event.target.value as InviteRole)}
              >
                {INVITE_ROLES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={role === "viewer" ? false : uploadEnabled}
                disabled={role === "viewer"}
                onChange={(event) => setUploadEnabled(event.target.checked)}
              />{" "}
              Upload enabled
            </label>
          </div>
          <Button
            type="button"
            variant="primary"
            onClick={() => inviteMutation.mutate()}
          >
            Create invitation
          </Button>
          {created ? (
            <dl>
              <dt>invitation_id</dt>
              <dd>
                <CodeText value={created.invitation_id} />
              </dd>
              <dt>email</dt>
              <dd>
                <UserText value={created.email} />
              </dd>
              <dt>role</dt>
              <dd>
                <UserText value={created.role} />
              </dd>
              <dt>token delivery</dt>
              <dd data-testid="invite-mail-only">{INVITE_TOKEN_MAIL_ONLY}</dd>
            </dl>
          ) : null}
        </section>
      ) : (
        <p className={styles.muted}>
          Invite create is hidden for this role. The helper still 403s on the
          server.
        </p>
      )}

      {canOffboard ? (
        <section className={styles.panel} data-testid="offboard-form" aria-label="Offboard">
          <h2>Offboard</h2>
          <LimitationCallout tone="warning">
            {OFFBOARD_IRREVERSIBLE_COPY}
          </LimitationCallout>
          <Input
            label="Subject user_id"
            value={subjectUserId}
            onChange={(event) => setSubjectUserId(event.target.value)}
          />
          <Button
            type="button"
            variant="danger"
            onClick={() => offboardMutation.mutate()}
          >
            Offboard user
          </Button>
          {offboarded ? (
            <dl>
              <dt>request_id</dt>
              <dd>
                <CodeText value={offboarded.request_id} />
              </dd>
              <dt>subject_user_id</dt>
              <dd>
                <CodeText value={offboarded.subject_user_id} />
              </dd>
              <dt>completed_at</dt>
              <dd>
                <UserText value={offboarded.completed_at} />
              </dd>
            </dl>
          ) : null}
        </section>
      ) : (
        <p className={styles.muted}>
          Offboarding is hidden for this role. The server still denies the
          request.
        </p>
      )}
    </div>
  );
}
