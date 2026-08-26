/**
 * Invite create and offboard by known user id. No member directory. No bootstrap.
 */

"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { Button, PrimaryAction } from "../ui/button";
import { ConfirmDialog } from "../ui/confirm-dialog";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import { StatusBanner } from "../ui/status-banner";
import { CodeText, UserText } from "../ui/user-text";
import {
  createInvitation,
  fetchMe,
  offboardUser,
  type ApiAuth,
} from "../../lib/api";
import { INVITE_TOKEN_MAIL_ONLY, OFFBOARD_IRREVERSIBLE_COPY } from "../../lib/admin-copy";
import { useSession } from "../../lib/auth/session-provider";
import { mutationFailureBanner } from "../../lib/failure-copy";
import { sessionQueryKeys } from "../../lib/query-keys";
import { showInviteConvenience, showOffboardConvenience } from "../../lib/roles";
import {
  INVITE_ROLES,
  type CreateInvitationResponse,
  type InviteRole,
  type OffboardResponse,
} from "../../lib/types";
import styles from "./admin.module.css";

const ROLE_OPTIONS = INVITE_ROLES.map((item) => ({ value: item, label: item }));

/**
 * Team & access cards.
 *
 * @returns Invite and offboard forms. Helpers remain callable for forged-role tests.
 */
export function TeamAccessPanel() {
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const reviewRef = useRef<HTMLButtonElement>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InviteRole>("member");
  const [uploadEnabled, setUploadEnabled] = useState(false);
  const [subjectUserId, setSubjectUserId] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
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
      setConfirmOpen(false);
      setError(null);
    },
    onError: (caught: Error) => {
      setOffboarded(null);
      setError(mutationFailureBanner(caught));
    },
  });

  return (
    <div className={styles.stack}>
      {error ? (
        <StatusBanner kind="error" role="alert">
          {error}
        </StatusBanner>
      ) : null}

      {canInvite ? (
        <section className={styles.panel} data-testid="invite-form" aria-label="Invite user">
          <h2>Invite user</h2>
          <Input
            label="Email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Select
            label="Role"
            value={role}
            options={ROLE_OPTIONS}
            onChange={(event) => setRole(event.target.value as InviteRole)}
          />
          <label className={styles.checkRow}>
            <input
              type="checkbox"
              checked={role === "viewer" ? false : uploadEnabled}
              disabled={role === "viewer"}
              onChange={(event) => setUploadEnabled(event.target.checked)}
            />
            Upload access
          </label>
          <PrimaryAction
            type="button"
            data-action-id="admin.invite"
            pending={inviteMutation.isPending}
            pendingLabel="Sending…"
            onClick={() => inviteMutation.mutate()}
          >
            Send invitation
          </PrimaryAction>
          {created ? (
            <dl data-testid="invite-mail-only">
              <dt>Invitation ID</dt>
              <dd>
                <CodeText value={created.invitation_id} />
              </dd>
              <dt>Expires</dt>
              <dd>
                <UserText value={created.expires_at} />
              </dd>
              <dt>Token</dt>
              <dd>{INVITE_TOKEN_MAIL_ONLY}</dd>
            </dl>
          ) : null}
        </section>
      ) : null}

      {canOffboard ? (
        <section className={`${styles.panel} ${styles.dangerPanel}`} data-testid="offboard-form" aria-label="Offboard user">
          <h2>Offboard user</h2>
          <p className={styles.muted}>{OFFBOARD_IRREVERSIBLE_COPY}</p>
          <Input
            label="User ID"
            value={subjectUserId}
            onChange={(event) => setSubjectUserId(event.target.value)}
          />
          <Button
            ref={reviewRef}
            type="button"
            variant="dangerQuiet"
            data-action-id="admin.offboard"
            disabled={subjectUserId.trim() === ""}
            disabledReason={subjectUserId.trim() === "" ? "Enter a user ID." : undefined}
            onClick={() => setConfirmOpen(true)}
          >
            Review offboarding
          </Button>
          {offboarded ? (
            <dl data-testid="offboard-result">
              <dt>Subject</dt>
              <dd>
                <CodeText value={offboarded.subject_user_id} />
              </dd>
              <dt>Completed</dt>
              <dd>
                <UserText value={offboarded.completed_at} />
              </dd>
            </dl>
          ) : null}
        </section>
      ) : null}

      {confirmOpen ? (
        <ConfirmDialog
          title="Offboard this account?"
          danger
          pending={offboardMutation.isPending}
          pendingLabel="Offboarding…"
          confirmLabel="Offboard user"
          returnFocusRef={reviewRef}
          onClose={() => {
            if (!offboardMutation.isPending) {
              setConfirmOpen(false);
            }
          }}
          onConfirm={() => offboardMutation.mutate()}
        >
          <p>
            This disables{" "}
            <span className={styles.mono}>
              <UserText value={subjectUserId} />
            </span>{" "}
            and ends their sessions. {OFFBOARD_IRREVERSIBLE_COPY}
          </p>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
