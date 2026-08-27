/**
 * One tool catalog card with enable and per-card permission controls.
 */

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "../ui/button";
import { Select } from "../ui/select";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import { enableTool, setToolPermission, type ApiAuth } from "../../lib/api";
import { inviteRoleLabel, toolPermissionLabel } from "../../lib/admin-copy";
import { mutationFailureBanner } from "../../lib/failure-copy";
import {
  INVITE_ROLES,
  TOOL_PERMISSIONS,
  type InviteRole,
  type ToolCardResponse,
  type ToolPermission,
} from "../../lib/types";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

const ROLE_OPTIONS = INVITE_ROLES.map((item) => ({
  value: item,
  label: inviteRoleLabel(item),
}));
const PERMISSION_OPTIONS = TOOL_PERMISSIONS.map((item) => ({
  value: item,
  label: toolPermissionLabel(item),
}));

export type ToolCardProps = {
  /** Catalog card from `GET /tools`. */
  card: ToolCardResponse;
  /** Owner/admin convenience. Server still authorizes. */
  canMutate: boolean;
  /** Bearer wrapper, or null when signed out. */
  auth: ApiAuth | null;
  /** Tools query key prefix to invalidate after enable. */
  toolsQueryKey: readonly unknown[];
  /** Open the details drawer. */
  onDetails: (card: ToolCardResponse) => void;
  /** Surface a classified mutation failure. */
  onError: (message: string) => void;
};

/**
 * Render one tool card. Permission selects are local to this card.
 *
 * @param props - Card, auth, and mutation callbacks.
 * @returns Article. Enable posts `{ active }`; permissions post role + level.
 */
export function ToolCard({
  card,
  canMutate,
  auth,
  toolsQueryKey,
  onDetails,
  onError,
}: ToolCardProps) {
  const queryClient = useQueryClient();
  const [targetRole, setTargetRole] = useState<InviteRole>("member");
  const [permission, setPermission] = useState<ToolPermission>("read");

  const enableMutation = useMutation({
    mutationFn: async (active: boolean) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return enableTool(auth, card.tool_key, active);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: toolsQueryKey });
    },
    onError: (caught: Error) => onError(mutationFailureBanner(caught)),
  });

  const permissionMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return setToolPermission(auth, card.tool_key, {
        target_role: targetRole,
        permission,
      });
    },
    onError: (caught: Error) => onError(mutationFailureBanner(caught)),
  });

  return (
    <article className={styles.card}>
      <h2>
        <UserText value={card.short_name} />
      </h2>
      <p className={styles.muted}>
        <UserText value={card.version_label} />
      </p>
      <p>
        <UserText value={card.purpose} />
      </p>
      <StatusPill
        tone={card.active ? "success" : "neutral"}
        status={card.active ? "Enabled" : "Disabled"}
      />
      {canMutate ? (
        <div className={styles.cardActions} data-testid={`tool-enable-${card.tool_key}`}>
          <Select
            label="Role"
            value={targetRole}
            options={ROLE_OPTIONS}
            onChange={(event) => setTargetRole(event.target.value as InviteRole)}
          />
          <Select
            label="Permission"
            value={permission}
            options={PERMISSION_OPTIONS}
            onChange={(event) => setPermission(event.target.value as ToolPermission)}
          />
          <Button
            type="button"
            data-action-id="admin.tools.enable"
            pending={enableMutation.isPending}
            pendingLabel="Saving…"
            onClick={() => enableMutation.mutate(!card.active)}
          >
            {card.active ? "Disable" : "Enable"}
          </Button>
          <Button
            type="button"
            data-action-id="admin.tools.permissions"
            pending={permissionMutation.isPending}
            pendingLabel="Saving…"
            onClick={() => permissionMutation.mutate()}
          >
            Save permission
          </Button>
        </div>
      ) : null}
      <Button
        type="button"
        data-action-id="admin.tools.details"
        onClick={() => onDetails(card)}
      >
        View details
      </Button>
    </article>
  );
}
