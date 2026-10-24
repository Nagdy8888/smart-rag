/**
 * Admin workspace: Team, Tools, Names & aliases, Usage, and Evaluation.
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
import { Select } from "../ui/select";
import { EvaluationPanel } from "../evaluation/evaluation-panel";
import { TeamAccessPanel } from "./team-access-panel";
import { ToolsPanel } from "./tools-panel";
import { UsagePanel } from "./usage-panel";
import { fetchMeta, listEntityRules, type ApiAuth } from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { pdfEvalCapability } from "../../lib/eval-workspace";
import { publicQueryKeys, sessionQueryKeys } from "../../lib/query-keys";
import {
  parseAdminTab,
  visibleAdminTabs,
  type AdminTab,
} from "../../lib/shell-navigation";
import styles from "./admin-shell.module.css";

const TAB_LABELS: Record<AdminTab, string> = {
  team: "Team & access",
  tools: "Tools",
  usage: "Usage",
  evaluation: "Evaluation",
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
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const metaQuery = useQuery({
    queryKey: publicQueryKeys.meta,
    queryFn: () => fetchMeta(),
    retry: false,
  });
  const pdfEval = pdfEvalCapability(metaQuery.data);
  const tabs = visibleAdminTabs(pdfEval);
  const tab = parseAdminTab(searchParams.get("tab") ?? undefined, pdfEval);
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
    const last = tabs.length - 1;
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
    const id = tabs[next];
    if (id) {
      router.replace(`/admin?tab=${id}`);
      document.getElementById(`admin-tab-${id}`)?.focus();
    }
  }

  if (!session.ready || accessToken === null) {
    return (
      <div className={styles.page}>
        <PageHeader />
        <p className={styles.muted}>Sign in to manage this workspace.</p>
      </div>
    );
  }

  if (gateQuery.isPending) {
    return (
      <div className={styles.page}>
        <PageHeader description="Manage people, tools, search names, and usage." />
        <Spinner label="Checking access" />
      </div>
    );
  }

  const denied =
    gateQuery.error instanceof Error && gateQuery.error.message === "forbidden";
  if (denied) {
    return (
      <div className={styles.page}>
        <PageHeader />
        <ErrorState
          title="You don’t have access."
          message="Only owners and admins can open this page."
        />
      </div>
    );
  }

  if (gateQuery.error) {
    return (
      <div className={styles.page}>
        <PageHeader />
        <ErrorState title="Something went wrong." message="The request could not be completed. Try again." />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.intro}>
        <div>
          <h2>Workspace settings</h2>
          <p>People, agent tools, and usage.</p>
        </div>
      </header>
      <HandshakeBanner />
      <div className={styles.sectionNav}>
      <div className={styles.mobileSections}><Select label="Admin section" fullWidth value={tab} options={tabs.map((id) => ({ value: id, label: TAB_LABELS[id] }))} onChange={(event) => router.replace(`/admin?tab=${event.target.value}`)} /></div>
      <div role="tablist" aria-label="Admin sections" className={`${styles.tabList} ${styles.desktopSections}`}>
        {tabs.map((id, index) => {
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
      </div>
      <div
        role="tabpanel"
        id={`admin-panel-${tab}`}
        aria-labelledby={`admin-tab-${tab}`}
        className={styles.tabPanel}
      >
        {tab === "team" ? <TeamAccessPanel /> : null}
        {tab === "tools" ? <ToolsPanel /> : null}
        {tab === "usage" ? <UsagePanel /> : null}
        {tab === "evaluation" ? <EvaluationPanel /> : null}
      </div>
    </div>
  );
}
