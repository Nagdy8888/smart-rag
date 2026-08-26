/**
 * Production console shell: skip link, 232px/72px nav rail, 56px top bar, main.
 *
 * Navigation is not an authorization boundary. See `client-authorization.ts`.
 */

"use client";

import { useState, type ReactNode } from "react";
import {
  CLIENT_NAV_IS_NOT_AUTHORIZATION,
  hiddenNavImpliesForbidden,
} from "../../lib/client-authorization";
import {
  NAV_EXPANDED_STORAGE_KEY,
  defaultNavExpanded,
  readBooleanPreference,
  writeBooleanPreference,
} from "../../lib/layout-preferences";
import { AppNav, ConsoleTopbar } from "./app-nav";
import { Button } from "./button";
import { Icon } from "./icon";
import styles from "./app-shell.module.css";

export type AppShellProps = {
  /** Main landmark content. */
  children: ReactNode;
};

/**
 * Render the ink-rail console chrome.
 *
 * @param props - Shell children.
 * @returns Landmark structure with English LTR chrome.
 * @remarks
 * Security: omitting nav items does not imply HTTP 403.
 * `CLIENT_NAV_IS_NOT_AUTHORIZATION` is true. The desktop expand state is
 * stored in localStorage. `data-expanded` and the expanded/collapsed
 * classes may differ on hydrate.
 */
export function AppShell({ children }: AppShellProps) {
  const [navExpanded, setNavExpanded] = useState(() =>
    readBooleanPreference(NAV_EXPANDED_STORAGE_KEY, defaultNavExpanded()),
  );

  /**
   * Toggle the desktop console rail and persist the choice.
   */
  function toggleNavExpanded(): void {
    setNavExpanded((current) => {
      const next = !current;
      writeBooleanPreference(NAV_EXPANDED_STORAGE_KEY, next);
      return next;
    });
  }

  const toggleLabel = navExpanded ? "Collapse navigation" : "Expand navigation";

  return (
    <div className={styles.shell}>
      <a className={styles.skipLink} href="#main" data-action-id="shell.skip">
        Skip to main content
      </a>
      <div className={styles.layout}>
        <nav
          className={[
            styles.nav,
            navExpanded ? styles.navIsExpanded : styles.navIsCollapsed,
          ].join(" ")}
          aria-label="Console"
          data-testid="app-shell-nav"
          data-expanded={navExpanded ? "true" : "false"}
          suppressHydrationWarning
        >
          <div className={styles.brand}>
            <span className={styles.brandMark} aria-hidden="true">
              <Icon name="spark" />
            </span>
            <span className={styles.brandText}>
              <p className={styles.brandName}>Smart RAG</p>
            </span>
          </div>
          <AppNav />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={styles.navToggle}
            aria-expanded={navExpanded}
            aria-label={toggleLabel}
            data-action-id="shell.nav_toggle"
            onClick={toggleNavExpanded}
          >
            <Icon name={navExpanded ? "panelCollapse" : "panelExpand"} />
          </Button>
        </nav>
        <div className={styles.content}>
          <header className={styles.topbar}>
            <ConsoleTopbar />
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
