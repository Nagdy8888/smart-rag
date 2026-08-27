/**
 * Invite, list workspace people, and offboard by user id.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { Button, PrimaryAction } from "../ui/button";
import { ConfirmDialog } from "../ui/confirm-dialog";
import { DataTable } from "../ui/data-table";
import { EmptyState } from "../ui/empty-state";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import { Spinner } from "../ui/spinner";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import { CodeText, UserText } from "../ui/user-text";
import { createInvitation, listWorkspaceUsers, offboardUser } from "../../lib/api";
import {
  INVITE_TOKEN_MAIL_ONLY,
  OFFBOARD_IRREVERSIBLE_COPY,
  WORKSPACE_PEOPLE_COPY,
  inviteRoleLabel,
} from "../../lib/admin-copy";
import { useApiAuth } from "../../lib/auth/use-api-auth";
import { useSession } from "../../lib/auth/session-provider";
import { mutationFailureBanner } from "../../lib/failure-copy";
import { useCurrentUser } from "../../lib/hooks/use-current-user";
import { sessionQueryKeys } from "../../lib/query-keys";
import { showInviteConvenience, showOffboardConvenience } from "../../lib/roles";
import {
  INVITE_ROLES,
  type CreateInvitationResponse,
  type InviteRole,
  type OffboardResponse,
  type PendingInvitation,
  type WorkspaceMember,
} from "../../lib/types";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

const ROLE_OPTIONS = INVITE_ROLES.map((item) => ({
  value: item,
  label: inviteRoleLabel(item),
}));

/**
 * Format an ISO timestamp for the team tables.
 *
 * @param value - ISO string or null.
 * @returns Locale string, or an em dash.
 */
function formatWhen(value: string | null): string {
  if (value === null || value === "") {
    return "—";
  }
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return new Date(parsed).toLocaleString();
}

/**
 * Team & access cards plus the authorized people list.
 *
 * @returns Invite, directory, and offboard forms. Helpers remain callable.
 */
export function TeamAccessPanel() {
  const session = useSession();
  const auth = useApiAuth();
  const queryClient = useQueryClient();
  const keys = sessionQueryKeys(session.accessToken);
  const { currentUser, currentUserPending } = useCurrentUser();
  const reviewRef = useRef<HTMLButtonElement>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<InviteRole>("member");
  const [uploadEnabled, setUploadEnabled] = useState(false);
  const [subjectUserId, setSubjectUserId] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [created, setCreated] = useState<CreateInvitationResponse | null>(null);
  const [offboarded, setOffboarded] = useState<OffboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canInvite = showInviteConvenience(currentUser?.role);
  const canOffboard = showOffboardConvenience(currentUser?.role);
  const canListPeople = canInvite || canOffboard;

  const directoryQuery = useQuery({
    queryKey: keys.workspaceUsers,
    queryFn: () => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return listWorkspaceUsers(auth);
    },
    enabled: auth !== null && canListPeople,
  });

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
      void queryClient.invalidateQueries({ queryKey: keys.workspaceUsers });
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
      void queryClient.invalidateQueries({ queryKey: keys.workspaceUsers });
    },
    onError: (caught: Error) => {
      setOffboarded(null);
      setError(mutationFailureBanner(caught));
    },
  });

  const memberColumns = useMemo(
    () => [
      {
        id: "person",
        header: "Person",
        cell: (row: WorkspaceMember) => (
          <div>
            <UserText value={row.email || row.display_name || row.user_id} />
            {row.display_name && row.email ? (
              <p className={styles.muted}>
                <UserText value={row.display_name} />
              </p>
            ) : null}
          </div>
        ),
      },
      {
        id: "role",
        header: "Role",
        cell: (row: WorkspaceMember) => (
          <UserText value={inviteRoleLabel(row.role)} />
        ),
      },
      {
        id: "upload",
        header: "Upload",
        cell: (row: WorkspaceMember) => (
          <UserText value={row.upload_enabled ? "Yes" : "No"} />
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: (row: WorkspaceMember) => {
          const disabled = row.disabled_at !== null;
          return (
            <StatusPill
              status={disabled ? "Disabled" : "Active"}
              tone={disabled ? "warning" : "success"}
            />
          );
        },
      },
      {
        id: "id",
        header: "User ID",
        cell: (row: WorkspaceMember) => <CodeText value={row.user_id} />,
      },
      {
        id: "actions",
        header: "Actions",
        cell: (row: WorkspaceMember) => {
          const isSelf = row.user_id === currentUser?.user_id;
          const alreadyOffboarded = row.disabled_at !== null;
          if (!canOffboard || isSelf || alreadyOffboarded) {
            return (
              <span className={styles.muted}>
                {isSelf ? "You" : alreadyOffboarded ? "Disabled" : "—"}
              </span>
            );
          }
          return (
            <Button
              type="button"
              variant="dangerQuiet"
              size="compact"
              data-action-id="admin.offboard"
              onClick={() => {
                setSubjectUserId(row.user_id);
                setConfirmOpen(true);
              }}
            >
              Offboard
            </Button>
          );
        },
      },
    ],
    [canOffboard, currentUser?.user_id],
  );

  const invitationColumns = useMemo(
    () => [
      {
        id: "email",
        header: "Email",
        cell: (row: PendingInvitation) => <UserText value={row.email} />,
      },
      {
        id: "role",
        header: "Role",
        cell: (row: PendingInvitation) => (
          <UserText value={inviteRoleLabel(row.role)} />
        ),
      },
      {
        id: "upload",
        header: "Upload",
        cell: (row: PendingInvitation) => (
          <UserText value={row.upload_enabled ? "Yes" : "No"} />
        ),
      },
      {
        id: "expires",
        header: "Expires",
        cell: (row: PendingInvitation) => {
          const expired = Date.parse(row.expires_at) < Date.now();
          return (
            <div>
              <UserText value={formatWhen(row.expires_at)} />
              {expired ? (
                <p className={styles.muted}>
                  <StatusPill status="Expired" tone="warning" />
                </p>
              ) : null}
            </div>
          );
        },
      },
    ],
    [],
  );

  if (currentUserPending) {
    return <Spinner label="Loading team access" />;
  }

  const directoryError =
    directoryQuery.error instanceof Error
      ? mutationFailureBanner(directoryQuery.error)
      : null;
  const members = directoryQuery.data?.members ?? [];
  const pending = directoryQuery.data?.pending_invitations ?? [];

  return (
    <div className={styles.stack}>
      <p className={styles.panelLead}>{WORKSPACE_PEOPLE_COPY}</p>
      {error ? (
        <StatusBanner kind="error" role="alert">
          {error}
        </StatusBanner>
      ) : null}
      {directoryError ? (
        <StatusBanner kind="error" role="alert">
          {directoryError}
        </StatusBanner>
      ) : null}

      {canListPeople ? (
        <section className={styles.panel} aria-label="Workspace people">
          <h2>Workspace people</h2>
          {directoryQuery.isPending ? <Spinner label="Loading people" /> : null}
          {!directoryQuery.isPending && members.length === 0 ? (
            <EmptyState
              title="No workspace accounts yet."
              body="Send an invitation. After the person accepts, they appear here."
            />
          ) : null}
          {members.length > 0 ? (
            <DataTable
              caption="Workspace people"
              columns={memberColumns}
              rows={members}
              getRowId={(row) => row.user_id}
            />
          ) : null}
        </section>
      ) : null}

      {canListPeople && pending.length > 0 ? (
        <section className={styles.panel} aria-label="Pending invitations">
          <h2>Pending invitations</h2>
          <DataTable
            caption="Pending invitations"
            columns={invitationColumns}
            rows={pending}
            getRowId={(row) => row.invitation_id}
          />
        </section>
      ) : null}

      <div className={styles.teamGrid}>
      {canInvite ? (
        <section className={styles.panel} data-testid="invite-form" aria-label="Invite user">
          <h2>Invite user</h2>
          <Input
            label="Email"
            type="email"
            fullWidth
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <Select
            label="Role"
            value={role}
            fullWidth
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
            className={styles.stretchAction}
            data-action-id="admin.invite"
            pending={inviteMutation.isPending}
            pendingLabel="Sending…"
            onClick={() => inviteMutation.mutate()}
          >
            Send invitation
          </PrimaryAction>
          {created ? (
            <dl className={styles.dl} data-testid="invite-mail-only">
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
            fullWidth
            value={subjectUserId}
            onChange={(event) => setSubjectUserId(event.target.value)}
          />
          <Button
            ref={reviewRef}
            type="button"
            variant="dangerQuiet"
            className={styles.stretchAction}
            data-action-id="admin.offboard"
            disabled={subjectUserId.trim() === ""}
            disabledReason={subjectUserId.trim() === "" ? "Enter a user ID." : undefined}
            onClick={() => setConfirmOpen(true)}
          >
            Review offboarding
          </Button>
          {offboarded ? (
            <dl className={styles.dl} data-testid="offboard-result">
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
      </div>

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
