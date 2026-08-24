/**
 * Tool catalog for any member. Enable/permissions are owner/admin convenience.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { HandshakeBanner } from "./auth/auth-screens";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { StatusBanner } from "./ui/status-banner";
import { StatusPill } from "./ui/status-pill";
import { CodeText, UserText } from "./ui/user-text";
import {
  enableTool,
  fetchMe,
  listTools,
  seedTool,
  setToolPermission,
  type ApiAuth,
} from "../lib/api";
import { useSession } from "../lib/auth/session-provider";
import { mutationFailureBanner } from "../lib/failure-copy";
import { sessionQueryKeys } from "../lib/query-keys";
import { showToolEnableConvenience } from "../lib/roles";
import {
  INVITE_ROLES,
  TOOL_PERMISSIONS,
  type InviteRole,
  type ToolPermission,
} from "../lib/types";
import styles from "./admin/admin.module.css";

/**
 * Render the permission-filtered tool catalog.
 *
 * @returns Tools surface.
 * @remarks
 * Unauthorized names are omitted by FastAPI. This UI does not invent
 * redacted titles. Enable remains callable for viewers; the server 403s.
 */
export function ToolsApp() {
  const queryClient = useQueryClient();
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const [filter, setFilter] = useState("");
  const [seedKey, setSeedKey] = useState("");
  const [seedName, setSeedName] = useState("");
  const [targetRole, setTargetRole] = useState<InviteRole>("member");
  const [permission, setPermission] = useState<ToolPermission>("read");
  const [outcome, setOutcome] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const meQuery = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });
  const toolsQuery = useQuery({
    queryKey: keys.tools,
    queryFn: () => listTools(auth as ApiAuth),
    enabled: auth !== null,
  });
  const canMutate = showToolEnableConvenience(meQuery.data?.role);

  const enableMutation = useMutation({
    mutationFn: async (input: { toolKey: string; active: boolean }) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return enableTool(auth, input.toolKey, input.active);
    },
    onSuccess: async (result, input) => {
      setError(null);
      setOutcome(
        `enable ${input.toolKey} active=${String(input.active)} id=${result.id}`,
      );
      await queryClient.invalidateQueries({ queryKey: keys.tools });
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
    onSuccess: (result, toolKey) => {
      setError(null);
      setOutcome(
        `permission ${toolKey} ${targetRole}/${permission} id=${result.id}`,
      );
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const seedMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return seedTool(auth, { tool_key: seedKey, display_name: seedName });
    },
    onSuccess: async (result) => {
      setError(null);
      setOutcome(`seed id=${result.id}`);
      await queryClient.invalidateQueries({ queryKey: keys.tools });
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const cards = (toolsQuery.data ?? []).filter((card) => {
    if (filter.trim() === "") {
      return true;
    }
    const needle = filter.trim().toLowerCase();
    return (
      card.tool_key.toLowerCase().includes(needle) ||
      card.short_name.toLowerCase().includes(needle)
    );
  });

  return (
    <div className={styles.shell}>
      <header className={styles.pageHeader}>
        <div>
          <h2>Tools</h2>
          <p className={styles.pageLead}>
            Optional tools available to your role. Enabling a tool still
            requires server authorization.
          </p>
        </div>
      </header>
      <HandshakeBanner />
      {error ? (
        <StatusBanner kind="error" role="alert">
          {error}
        </StatusBanner>
      ) : null}
      {outcome ? (
        <StatusBanner kind="success" role="status">
          {outcome}
        </StatusBanner>
      ) : null}
      <Input
        label="Filter"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
      />
      <div className={styles.cards}>
        {cards.map((card) => (
          <article key={card.tool_key} className={styles.card}>
            <h2>
              <UserText value={card.short_name} />
            </h2>
            <dl>
              <dt>tool_key</dt>
              <dd>
                <CodeText value={card.tool_key} />
              </dd>
              <dt>version</dt>
              <dd>
                <UserText value={card.version_label} />
              </dd>
              <dt>purpose</dt>
              <dd>
                <UserText value={card.purpose} />
              </dd>
              <dt>required_role</dt>
              <dd>
                <UserText value={card.required_role} />
              </dd>
              <dt>risk_class</dt>
              <dd>
                <UserText value={card.risk_class} />
              </dd>
              <dt>active</dt>
              <dd>
                <StatusPill
                  tone={card.active ? "success" : "neutral"}
                  status={card.active ? "enabled" : "disabled"}
                />
              </dd>
            </dl>
            {canMutate ? (
              <div className={styles.row} data-testid={`tool-enable-${card.tool_key}`}>
                <Button
                  type="button"
                  onClick={() =>
                    enableMutation.mutate({
                      toolKey: card.tool_key,
                      active: !card.active,
                    })
                  }
                >
                  {card.active ? "Disable" : "Enable"}
                </Button>
                <label>
                  Role
                  <select
                    value={targetRole}
                    onChange={(event) =>
                      setTargetRole(event.target.value as InviteRole)
                    }
                  >
                    {INVITE_ROLES.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Permission
                  <select
                    value={permission}
                    onChange={(event) =>
                      setPermission(event.target.value as ToolPermission)
                    }
                  >
                    {TOOL_PERMISSIONS.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
                <Button
                  type="button"
                  onClick={() => permissionMutation.mutate(card.tool_key)}
                >
                  Set permission
                </Button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
      {cards.length === 0 && !toolsQuery.isPending ? (
        <p className={styles.muted}>
          No tools visible for this role. Unauthorized names are omitted, not
          redacted.
        </p>
      ) : null}
      {canMutate ? (
        <section className={styles.panel} aria-label="Seed tool">
          <h2>Seed catalog</h2>
          <div className={styles.formGrid}>
            <Input
              label="tool_key"
              value={seedKey}
              onChange={(event) => setSeedKey(event.target.value)}
            />
            <Input
              label="display_name"
              value={seedName}
              onChange={(event) => setSeedName(event.target.value)}
            />
          </div>
          <Button type="button" onClick={() => seedMutation.mutate()}>
            Seed tool
          </Button>
        </section>
      ) : (
        <p className={styles.muted}>
          Enable and seed controls are hidden. The server still denies the
          request.
        </p>
      )}
    </div>
  );
}
