/**
 * Tool catalog with search `q`, enable/disable, and permission mutations.
 * Seeding is omitted from ordinary product UI.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState, type FormEvent } from "react";
import { Button } from "../ui/button";
import { Drawer } from "../ui/drawer";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import { CodeText, UserText } from "../ui/user-text";
import {
  enableTool,
  fetchMe,
  listTools,
  setToolPermission,
  type ApiAuth,
} from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { mutationFailureBanner } from "../../lib/failure-copy";
import { sessionQueryKeys } from "../../lib/query-keys";
import { showToolEnableConvenience } from "../../lib/roles";
import {
  INVITE_ROLES,
  TOOL_PERMISSIONS,
  type InviteRole,
  type ToolCardResponse,
  type ToolPermission,
} from "../../lib/types";
import styles from "./admin.module.css";

const ROLE_OPTIONS = INVITE_ROLES.map((item) => ({ value: item, label: item }));
const PERMISSION_OPTIONS = TOOL_PERMISSIONS.map((item) => ({
  value: item,
  label: item,
}));

/**
 * Render searchable tool cards.
 *
 * @returns Tools tab. `listTools` URL-encodes `q`. `enableTool` remains for forged tests.
 */
export function ToolsPanel() {
  const queryClient = useQueryClient();
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const detailsRef = useRef<HTMLButtonElement>(null);
  const [draft, setDraft] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [targetRole, setTargetRole] = useState<InviteRole>("member");
  const [permission, setPermission] = useState<ToolPermission>("read");
  const [details, setDetails] = useState<ToolCardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const meQuery = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });
  const toolsQuery = useQuery({
    queryKey: keys.tools(submitted),
    queryFn: () => listTools(auth as ApiAuth, submitted),
    enabled: auth !== null,
  });
  const canMutate = showToolEnableConvenience(meQuery.data?.role);
  const cards = toolsQuery.data ?? [];

  const enableMutation = useMutation({
    mutationFn: async (input: { toolKey: string; active: boolean }) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return enableTool(auth, input.toolKey, input.active);
    },
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["tools"] });
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const permissionMutation = useMutation({
    mutationFn: async (toolKey: string) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return setToolPermission(auth, toolKey, {
        target_role: targetRole,
        permission,
      });
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
    onSuccess: () => setError(null),
  });

  /**
   * Submit search. Empty `q` lists the unfiltered catalog.
   *
   * @param event - Form submit.
   */
  function onSearch(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setSubmitted(draft.trim().slice(0, 64));
  }

  return (
    <div className={styles.stack}>
      {error ? (
        <StatusBanner kind="error" role="alert">
          {error}
        </StatusBanner>
      ) : null}
      <form className={styles.toolbar} onSubmit={onSearch}>
        <Input
          label="Search tools"
          value={draft}
          leadingIcon="search"
          onChange={(event) => setDraft(event.target.value)}
        />
        <Button type="submit" data-action-id="admin.tools.search">Search</Button>
        <p className={styles.muted}>{String(cards.length)} tools</p>
      </form>
      <div className={styles.toolGrid}>
        {cards.map((card) => (
          <article key={card.tool_key} className={styles.card}>
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
              status={card.active ? "enabled" : "disabled"}
            />
            {canMutate ? (
              <div className={styles.row} data-testid={`tool-enable-${card.tool_key}`}>
                <Select
                  label="Permission"
                  value={`${targetRole}:${permission}`}
                  options={ROLE_OPTIONS.flatMap((role) =>
                    PERMISSION_OPTIONS.map((perm) => ({
                      value: `${role.value}:${perm.value}`,
                      label: `${role.label} ${perm.label}`,
                    })),
                  )}
                  onChange={(event) => {
                    const [nextRole, nextPerm] = event.target.value.split(":");
                    if (nextRole) {
                      setTargetRole(nextRole as InviteRole);
                    }
                    if (nextPerm) {
                      setPermission(nextPerm as ToolPermission);
                    }
                  }}
                />
                <Button
                  type="button"
                  data-action-id="admin.tools.enable"
                  pending={enableMutation.isPending}
                  pendingLabel="Saving…"
                  onClick={() =>
                    enableMutation.mutate({
                      toolKey: card.tool_key,
                      active: !card.active,
                    })
                  }
                >
                  {card.active ? "Disable" : "Enable"}
                </Button>
                <Button
                  type="button"
                  data-action-id="admin.tools.permissions"
                  pending={permissionMutation.isPending}
                  pendingLabel="Saving…"
                  onClick={() => permissionMutation.mutate(card.tool_key)}
                >
                  Save permission
                </Button>
              </div>
            ) : null}
            <Button
              ref={detailsRef}
              type="button"
              data-action-id="admin.tools.details"
              onClick={() => setDetails(card)}
            >
              View details
            </Button>
          </article>
        ))}
      </div>
      {cards.length === 0 && !toolsQuery.isPending ? (
        <p className={styles.muted}>
          No tools visible for this role. Unauthorized names are omitted, not redacted.
        </p>
      ) : null}
      {details ? (
        <Drawer
          title="Tool details."
          onClose={() => setDetails(null)}
          returnFocusRef={detailsRef}
        >
          <dl className={styles.dl}>
            <dt>tool_key</dt>
            <dd>
              <CodeText value={details.tool_key} />
            </dd>
            <dt>version</dt>
            <dd>
              <UserText value={details.version_label} />
            </dd>
            <dt>purpose</dt>
            <dd>
              <UserText value={details.purpose} />
            </dd>
            <dt>required_role</dt>
            <dd>
              <UserText value={details.required_role} />
            </dd>
            <dt>risk_class</dt>
            <dd>
              <UserText value={details.risk_class} />
            </dd>
            <dt>active</dt>
            <dd>
              <UserText value={String(details.active)} />
            </dd>
          </dl>
        </Drawer>
      ) : null}
    </div>
  );
}
