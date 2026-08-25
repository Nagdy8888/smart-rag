/**
 * Admin workspace: Team, Tools, Curation, and Usage behind `?tab=`.
 * Member/viewer visits confirm denial with an owner/admin GET before chrome.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, type KeyboardEvent } from "react";
import { HandshakeBanner } from "../auth/auth-screens";
import { ErrorState } from "../ui/error-state";
import { PageHeader } from "../ui/page-header";
import { Spinner } from "../ui/spinner";
import { CurationPanel } from "./curation-panel";
import { TeamAccessPanel } from "./team-access-panel";
import { ToolsPanel } from "./tools-panel";
import { UsagePanel } from "./usage-panel";
import { listEntityRules, type ApiAuth } from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { sessionQueryKeys } from "../../lib/query-keys";
import { ADMIN_TABS, parseAdminTab, type AdminTab } from "../../lib/shell-navigation";
import styles from "./admin.module.css";

const TAB_LABELS: Record<AdminTab, string> = {
  team: "Team & access",
  tools: "Tools",
  curation: "Curation",
  usage: "Usage",
};

/**
 * Render Admin tabs after a real owner/admin confirmation.
 *
 * @returns Tablist plus selected panel, or a permission ErrorState.
 */
export function AdminApp() {
  const session = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = parseAdminTab(searchParams.get("tab") ?? undefined);
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const gateQuery = useQuery({
    queryKey: keys.entityRules,
    queryFn: () => listEntityRules(auth as ApiAuth),
    enabled: auth !== null,
    retry: false,
  });

  /**
   * Move among tabs with arrows and update `?tab=`.
   *
   * @param event - Keyboard event from the tablist.
   * @param index - Focused tab index.
   */
  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number): void {
    const last = ADMIN_TABS.length - 1;
    let next = index;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      next = index === last ? 0 : index + 1;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      next = index === 0 ? last : index - 1;
    } else if (event.key === "Home") {
      next = 0;
    } else if (event.key === "End") {
      next = last;
    } else {
      return;
    }
    event.preventDefault();
    const id = ADMIN_TABS[next];
    if (id) {
      router.replace(`/admin?tab=${id}`);
    }
  }

  if (!session.ready || accessToken === null) {
    return (
      <div className={styles.page}>
        <PageHeader title="Admin." />
        <p className={styles.muted}>Sign in to manage this workspace.</p>
      </div>
    );
  }

  if (gateQuery.isPending) {
    return (
      <div className={styles.page}>
        <PageHeader
          title="Admin."
          description="Manage access, tools, retrieval curation, and usage."
        />
        <Spinner label="Checking access" />
      </div>
    );
  }

  const denied =
    gateQuery.error instanceof Error && gateQuery.error.message === "forbidden";
  if (denied) {
    return (
      <div className={styles.page}>
        <PageHeader title="Admin." />
        <ErrorState
          title="You don’t have access."
          message="This area is limited to owners and admins. The server denied the request."
        />
      </div>
    );
  }

  if (gateQuery.error) {
    return (
      <div className={styles.page}>
        <PageHeader title="Admin." />
        <ErrorState title="Something went wrong." message="The request could not be completed. Try again." />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <PageHeader
        title="Admin."
        description="Manage access, tools, retrieval curation, and usage."
      />
      <HandshakeBanner />
      <div role="tablist" aria-label="Admin sections" className={styles.tabList}>
        {ADMIN_TABS.map((id, index) => {
          const current = tab === id;
          return (
            <button
              key={id}
              type="button"
              role="tab"
              id={`admin-tab-${id}`}
              aria-selected={current}
              aria-controls={`admin-panel-${id}`}
              tabIndex={current ? 0 : -1}
              className={current ? styles.tabCurrent : styles.tab}
              data-action-id={`admin.tab.${id}`}
              data-testid={`admin-tab-${id}`}
              onClick={() => router.replace(`/admin?tab=${id}`)}
              onKeyDown={(event) => onTabKeyDown(event, index)}
            >
              {TAB_LABELS[id]}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`admin-panel-${tab}`}
        aria-labelledby={`admin-tab-${tab}`}
        className={styles.tabPanel}
      >
        {tab === "team" ? <TeamAccessPanel /> : null}
        {tab === "tools" ? <ToolsPanel /> : null}
        {tab === "curation" ? <CurationPanel /> : null}
        {tab === "usage" ? <UsagePanel /> : null}
      </div>
    </div>
  );
}
