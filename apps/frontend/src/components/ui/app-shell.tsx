/**
 * Production console shell: skip link, 280px desktop nav, main landmark.
 *
 * Packet 1 hosts the Phase 6 developer console at `/`. Navigation is not
 * an authorization boundary. See `client-authorization.ts`.
 */

import type { ReactNode } from "react";
import {
  CLIENT_NAV_IS_NOT_AUTHORIZATION,
  hiddenNavImpliesForbidden,
} from "../../lib/client-authorization";
import styles from "./app-shell.module.css";

export type AppShellProps = {
  /** Main landmark content. Typically `DeveloperApp` in packet 1. */
  children: ReactNode;
};

const NAV_ITEMS = [{ href: "/", label: "Console" }] as const;

/**
 * Render the high-density light application chrome.
 *
 * @param props - Shell children. No fetch or auth side effects.
 * @returns Landmark structure with English LTR chrome.
 * @remarks
 * Security: omitting future nav items does not imply HTTP 403.
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
          <p className={styles.brand}>Smart RAG</p>
          <ul className={styles.navList}>
            {NAV_ITEMS.map((item) => (
              <li key={item.href} className={styles.navRow}>
                <a href={item.href} aria-current="page">
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
          <p className={styles.navNote}>
            Nav visibility is convenience only. Server authorization is
            authoritative.
          </p>
        </nav>
        <main id="main" className={styles.main} tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
}

export { CLIENT_NAV_IS_NOT_AUTHORIZATION, hiddenNavImpliesForbidden };
