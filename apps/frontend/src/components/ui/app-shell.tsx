/**
 * Production console shell: light top bar and full-bleed main.
 *
 * Navigation is not an authorization boundary. See `client-authorization.ts`.
 */

"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { ACCOUNT_NAV_ITEM, ADMIN_NAV_ITEM, PRIMARY_NAV_ITEMS, navItemIsCurrent } from "../../lib/shell-navigation";
import {
  CLIENT_NAV_IS_NOT_AUTHORIZATION,
  hiddenNavImpliesForbidden,
} from "../../lib/client-authorization";
import { AppNav, ConsoleTopbar } from "./app-nav";
import navStyles from "./app-nav.module.css";
import layoutStyles from "./app-shell.module.css";
import topbarStyles from "./app-topbar.module.css";

const styles = { ...layoutStyles, ...navStyles, ...topbarStyles };

export type AppShellProps = {
  /** Main landmark content. */
  children: ReactNode;
};

/**
 * Render the console chrome: light top bar with word links and a full-bleed main.
 *
 * @param props - Shell children.
 * @returns Landmark structure with English LTR chrome.
 * @remarks
 * Security: omitting nav items does not imply HTTP 403.
 * `CLIENT_NAV_IS_NOT_AUTHORIZATION` is true.
 */
export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname() ?? "/";
  const title = [...PRIMARY_NAV_ITEMS, ADMIN_NAV_ITEM, ACCOUNT_NAV_ITEM]
    .find((item) => navItemIsCurrent(pathname, item.href))?.label ?? "Smart RAG";
  return (
    <div className={styles.shell}>
      <a className={styles.skipLink} href="#main" data-action-id="shell.skip">
        Skip to main content
      </a>
      <div className={styles.layout}>
        <header className={styles.topbar}>
          <div className={styles.brand}>
            <p className={styles.brandName}>Smart RAG</p>
          </div>
          <nav
            className={styles.nav}
            aria-label="Console"
            data-testid="app-shell-nav"
            data-expanded="true"
          >
            <AppNav />
          </nav>
          <div className={styles.topbarTools}>
            <ConsoleTopbar />
          </div>
        </header>
        <main id="main" className={styles.main} tabIndex={-1}>
          <h1 className={styles.srOnly}>{title}</h1>
          <div className={styles.plate}>{children}</div>
        </main>
      </div>
    </div>
  );
}

export { CLIENT_NAV_IS_NOT_AUTHORIZATION, hiddenNavImpliesForbidden };
