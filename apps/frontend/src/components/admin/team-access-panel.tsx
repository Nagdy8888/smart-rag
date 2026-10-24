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
import { UserText } from "../ui/user-text";
import { createInvitation, listWorkspaceUsers, offboardUser } from "../../lib/api";
import {
  INVITE_TOKEN_MAIL_ONLY,
  OFFBOARD_IRREVERSIBLE_COPY,
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
  const [subject, setSubject] = useState<WorkspaceMember | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("active");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [created, setCreated] = useState<CreateInvitationResponse | null>(null);
  const [offboarded, setOffboarded] = useState<OffboardResponse | null>(null);
  const [offboardedLabel, setOffboardedLabel] = useState("");
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
      setInviteOpen(false);
      setEmail("");
      setRole("member");
      setUploadEnabled(false);
      reviewRef.current?.focus();
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
      if (subject === null || subject.user_id === currentUser?.user_id) {
        throw new Error("invalid_subject");
      }
      return offboardUser(auth, subject.user_id);
    },
    onSuccess: (result) => {
      setOffboarded(result);
      setOffboardedLabel(subject?.email || subject?.display_name || result.subject_user_id);
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
              onClick={(event) => {
                reviewRef.current = event.currentTarget;
                setSubject(row);
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
  const matchingMembers = members.filter((member) => {
    const matchesStatus = statusFilter === "all" || (statusFilter === "active" ? member.disabled_at === null : member.disabled_at !== null);
    return matchesStatus && [member.email, member.display_name, member.role].some((value) => value?.toLowerCase().includes(search.trim().toLowerCase()));
  });

  return (
    <div className={styles.stack}>
      <div className={styles.taskHeader}>
        <div><h2>People & access</h2><p className={styles.panelLead}>Find a person, invite a teammate, or review their access.</p></div>
        {canInvite ? <Button type="button" variant="primary" aria-expanded={inviteOpen} aria-controls="team-invitation" onClick={(event) => {
          reviewRef.current = event.currentTarget;
          setInviteOpen((open) => !open);
        }} disabled={inviteMutation.isPending}>{inviteOpen ? "Close invitation" : "Invite teammate"}</Button> : null}
      </div>
      {error && !confirmOpen ? (
        <StatusBanner kind="error" role="alert">
          {error}
        </StatusBanner>
      ) : null}
      {directoryError ? (
        <StatusBanner kind="error" role="alert">
          {directoryError} <Button type="button" variant="secondary" onClick={() => { void directoryQuery.refetch(); }}>Retry people</Button>
        </StatusBanner>
      ) : null}

      {canInvite && inviteOpen ? (
        <form id="team-invitation" className={styles.panel} data-testid="invite-form" aria-label="Invite user" onSubmit={(event) => {
          event.preventDefault();
          if (!inviteMutation.isPending && email.trim()) inviteMutation.mutate();
        }}>
          <h2>Invite a teammate</h2><p className={styles.panelLead}>Choose what they can do. The invitation is delivered by email.</p>
          <Input
            label="Email"
            type="email"
            required
            autoFocus
            autoComplete="email"
            placeholder="teammate@company.com"
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
          <p className={styles.panelLead}>{role === "viewer" ? "Viewers can read and ask questions. Uploads are disabled." : role === "member" ? "Members can ask questions. Enable uploads only if they need to add documents." : "Owners and admins can manage workspace people, tools, and settings."}</p>
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
            type="submit"
            className={styles.stretchAction}
            data-action-id="admin.invite"
            pending={inviteMutation.isPending}
            pendingLabel="Sending…"
            disabled={!email.trim()}
          >
            Send invitation
          </PrimaryAction>
        </form>
      ) : null}
      {created ? (
        <StatusBanner kind="success" role="status">
          <span data-testid="invite-mail-only">Invitation sent to <UserText value={created.email} />. {INVITE_TOKEN_MAIL_ONLY}</span>
        </StatusBanner>
      ) : null}
      {offboarded ? <StatusBanner kind="success" role="status"><span data-testid="offboard-result">Access removed for <UserText value={offboardedLabel} />. Their sessions have ended.</span></StatusBanner> : null}
      {canListPeople ? (
        <section className={styles.panel} aria-label="Workspace people">
          <div className={styles.directoryTools}>
            <Input label="Find a person" fullWidth leadingIcon="search" type="search" placeholder="Search name, email, or role" value={search} onChange={(event) => setSearch(event.target.value)} />
            <Select label="Account status" value={statusFilter} options={[{ value: "active", label: "Active accounts" }, { value: "disabled", label: "Disabled accounts" }, { value: "all", label: "All accounts" }]} onChange={(event) => setStatusFilter(event.target.value)} />
            <p className={styles.muted} role="status">{directoryQuery.isPending ? "Loading people..." : directoryQuery.isError ? "People list unavailable" : `${matchingMembers.length} of ${members.length} people`}</p>
          </div>
          {directoryQuery.isPending ? <Spinner label="Loading people" /> : null}
          {directoryQuery.isSuccess && members.length === 0 ? (
            <EmptyState
              title="No workspace accounts yet."
              body="Send an invitation. After the person accepts, they appear here."
            />
          ) : null}
          {members.length > 0 && matchingMembers.length === 0 ? <><EmptyState title="No matching people." body="Try another name or change the account status filter." /><Button type="button" variant="secondary" onClick={() => { setSearch(""); setStatusFilter("all"); }}>Reset people filters</Button></> : null}
          {matchingMembers.length > 0 ? (
            <div className={styles.peopleDirectory}><DataTable
              variant="bare"
              caption="Workspace people"
              columns={memberColumns}
              rows={matchingMembers}
              getRowId={(row) => row.user_id}
            /></div>
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

      {confirmOpen && subject ? (
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
          {error ? <StatusBanner kind="error" role="alert">{error}</StatusBanner> : null}
          <p>
            This disables{" "}
            <span className={styles.mono}>
              <UserText value={subject?.email || subject?.display_name || subject?.user_id || "this person"} />
            </span>{" "}
            and ends their sessions. {OFFBOARD_IRREVERSIBLE_COPY}
          </p>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
