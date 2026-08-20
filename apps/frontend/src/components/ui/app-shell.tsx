/**
 * Production console shell: skip link, 280px desktop nav, top bar, main landmark.
 *
 * Navigation is not an authorization boundary. See `client-authorization.ts`.
 */

import type { ReactNode } from "react";
import {
  CLIENT_NAV_IS_NOT_AUTHORIZATION,
  hiddenNavImpliesForbidden,
} from "../../lib/client-authorization";
import { AppNav, ShellUser, TopbarTitle } from "./app-nav";
import { Icon } from "./icon";
import styles from "./app-shell.module.css";

export type AppShellProps = {
  /** Main landmark content. */
  children: ReactNode;
};

/**
 * Render the high-density light application chrome.
 *
 * @param props - Shell children. No fetch or auth side effects in this file.
 * @returns Landmark structure with English LTR chrome.
 * @remarks
 * Security: omitting nav items does not imply HTTP 403.
 * `CLIENT_NAV_IS_NOT_AUTHORIZATION` is true. Errors: none. Idempotent render.
 */
export function AppShell({ children }: AppShellProps) {
  return (
    <div className={styles.shell}>
      <a className={styles.skipLink} href="#main">
        Skip to main content
      </a>
      <div className={styles.layout}>
        <nav
          className={styles.nav}
          aria-label="Console"
          data-testid="app-shell-nav"
        >
          <div className={styles.brand}>
            <span className={styles.brandMark} aria-hidden="true">
              <Icon name="spark" />
            </span>
            <span className={styles.brandText}>
              <p className={styles.brandName}>Smart RAG</p>
              <p className={styles.brandSub}>Enterprise AI Console</p>
            </span>
          </div>
          <AppNav />
          <ShellUser />
        </nav>
        <div className={styles.content}>
          <header className={styles.topbar}>
            <TopbarTitle />
            <p className={styles.topbarMeta}>Workspace</p>
          </header>
          <main id="main" className={styles.main} tabIndex={-1}>
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}

export { CLIENT_NAV_IS_NOT_AUTHORIZATION, hiddenNavImpliesForbidden };
