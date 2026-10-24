/**
 * Tool catalog with search `q`, enable/disable, and permission mutations.
 * Seeding is omitted from ordinary product UI.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button } from "../ui/button";
import { Drawer } from "../ui/drawer";
import { EmptyState } from "../ui/empty-state";
import { Input } from "../ui/input";
import { Spinner } from "../ui/spinner";
import { StatusBanner } from "../ui/status-banner";
import { CodeText, UserText } from "../ui/user-text";
import { listTools } from "../../lib/api";
import { inviteRoleLabel } from "../../lib/admin-copy";
import { useApiAuth } from "../../lib/auth/use-api-auth";
import { mutationFailureBanner } from "../../lib/failure-copy";
import { useCurrentUser } from "../../lib/hooks/use-current-user";
import { sessionCacheScope, sessionQueryKeys } from "../../lib/query-keys";
import { showToolEnableConvenience } from "../../lib/roles";
import { useSession } from "../../lib/auth/session-provider";
import type { ToolCardResponse } from "../../lib/types";
import { ToolCard } from "./tool-card";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

/**
 * Render searchable tool cards.
 *
 * @returns Tools tab. `listTools` URL-encodes `q`. `enableTool` remains for forged tests.
 */
export function ToolsPanel() {
  const session = useSession();
  const auth = useApiAuth();
  const keys = sessionQueryKeys(session.accessToken);
  const [draft, setDraft] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [details, setDetails] = useState<ToolCardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { currentUser } = useCurrentUser();
  const toolsQuery = useQuery({
    queryKey: keys.tools(submitted),
    queryFn: () => listTools(auth!, submitted),
    enabled: auth !== null,
  });
  const canMutate = showToolEnableConvenience(currentUser?.role);
  const cards = toolsQuery.data ?? [];
  const toolsError =
    toolsQuery.error instanceof Error
      ? mutationFailureBanner(toolsQuery.error)
      : null;

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
      {toolsError ? (
        <StatusBanner kind="error" role="alert">
          {toolsError} <Button type="button" variant="secondary" onClick={() => { void toolsQuery.refetch(); }}>Retry tools</Button>
        </StatusBanner>
      ) : null}
      <form className={styles.toolbar} onSubmit={onSearch}>
        <Input
          label="Search tools"
          value={draft}
          leadingIcon="search"
          onChange={(event) => setDraft(event.target.value)}
        />
        <Button type="submit" data-action-id="admin.tools.search">
          Search
        </Button>
        {draft || submitted ? <Button type="button" variant="secondary" onClick={() => { setDraft(""); setSubmitted(""); }}>Clear search</Button> : null}
        <p className={styles.muted} role="status">{toolsQuery.isFetching ? "Searching tools..." : `${String(cards.length)} tools${submitted ? ` matching "${submitted}"` : ""}`}</p>
      </form>
      {toolsQuery.isPending ? <Spinner label="Loading tools" /> : null}
      <div className={styles.toolGrid}>
        {cards.map((card) => (
          <ToolCard
            key={card.tool_key}
            card={card}
            canMutate={canMutate}
            auth={auth}
            toolsQueryKey={["tools", sessionCacheScope(session.accessToken)]}
            onDetails={setDetails}
            onError={setError}
          />
        ))}
      </div>
      {cards.length === 0 && !toolsQuery.isPending && toolsQuery.error == null ? (
        <EmptyState
          title="No tools to show."
          body={
            submitted
              ? "Nothing matched this search."
              : "No tools are visible for this role."
          }
          icon="tools"
        />
      ) : null}
      {details ? (
        <Drawer
          title="Tool details"
          onClose={() => setDetails(null)}
        >
          <dl className={styles.dl}>
            <dt>Key</dt>
            <dd>
              <CodeText value={details.tool_key} />
            </dd>
            <dt>Version</dt>
            <dd>
              <UserText value={details.version_label} />
            </dd>
            <dt>Purpose</dt>
            <dd>
              <UserText value={details.purpose} />
            </dd>
            <dt>Required role</dt>
            <dd>
              <UserText value={inviteRoleLabel(details.required_role)} />
            </dd>
            <dt>Risk</dt>
            <dd>
              <UserText value={details.risk_class} />
            </dd>
            <dt>Status</dt>
            <dd>
              <UserText value={details.active ? "Enabled" : "Disabled"} />
            </dd>
          </dl>
        </Drawer>
      ) : null}
    </div>
  );
}
