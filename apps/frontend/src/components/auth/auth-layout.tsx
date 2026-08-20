/**
 * Focused public Auth layout. No console navigation.
 */

import type { ReactNode } from "react";
import { Icon } from "../ui/icon";
import styles from "./auth.module.css";

export type AuthLayoutProps = {
  /** Auth card or unavailable body. */
  children: ReactNode;
};

/**
 * Render brand chrome around Auth-direct pages.
 *
 * @param props - Route children.
 * @returns Skip link, brand, and `#main` landmark.
 * @remarks
 * URLs stay `/login` and siblings. Proxy/session behavior is unchanged.
 * No readiness panels or console nav.
 */
export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className={styles.page}>
      <a className={styles.skipLink} href="#main">
        Skip to main content
      </a>
      <div className={styles.brand}>
        <span className={styles.mark} aria-hidden="true">
          <Icon name="spark" />
        </span>
        <p className={styles.product}>Smart RAG</p>
        <p className={styles.subbrand}>Enterprise AI Console</p>
      </div>
      <main id="main" className={styles.main} tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
