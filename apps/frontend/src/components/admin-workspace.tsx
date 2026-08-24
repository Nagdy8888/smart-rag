/**
 * Admin workspace: compose Team, Tools, Curation, and Usage behind `?tab=`.
 *
 * Tab visibility is not authorization. FastAPI still enforces each mutation.
 */

"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CurationApp } from "./curation-app";
import { TeamApp } from "./team-app";
import { ToolsApp } from "./tools-app";
import { UsageApp } from "./usage-app";
import {
  ADMIN_TABS,
  parseAdminTab,
  type AdminTab,
} from "../lib/shell-navigation";
import styles from "./admin/admin.module.css";

const TAB_LABELS: Record<AdminTab, string> = {
  team: "Team",
  tools: "Tools",
  curation: "Curation",
  usage: "Usage",
};

/**
 * Render Admin tabs and the selected existing administration app.
 *
 * @returns Tab strip plus the matching app. Side effects: none besides child fetches.
 */
export function AdminWorkspace() {
  const searchParams = useSearchParams();
  const tab = parseAdminTab(searchParams.get("tab") ?? undefined);
  return (
    <div className={styles.shell}>
      <nav className={styles.tabList} aria-label="Admin sections">
        {ADMIN_TABS.map((id) => {
          const current = tab === id;
          return (
            <Link
              key={id}
              href={`/admin?tab=${id}`}
              className={current ? styles.tabCurrent : styles.tab}
              aria-current={current ? "page" : undefined}
              data-action-id={`admin.tab.${id}`}
              data-testid={`admin-tab-${id}`}
            >
              {TAB_LABELS[id]}
            </Link>
          );
        })}
      </nav>
      {tab === "team" ? <TeamApp /> : null}
      {tab === "tools" ? <ToolsApp /> : null}
      {tab === "curation" ? <CurationApp /> : null}
      {tab === "usage" ? <UsageApp /> : null}
    </div>
  );
}
