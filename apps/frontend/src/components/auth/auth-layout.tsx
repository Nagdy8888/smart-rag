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
 * Render a split Auth composition: gradient brand panel plus form surface.
 *
 * @param props - Route children.
 * @returns Skip link, brand panel, and `#main` landmark.
 * @remarks
 * URLs stay `/login` and siblings. Proxy/session behavior is unchanged.
 * The brand gradient is the approved exception from the no-gradient rule.
 */
export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className={styles.page}>
      <a className={styles.skipLink} href="#main" data-action-id="shell.skip">
        Skip to main content
      </a>
      <div className={styles.split}>
        <aside className={styles.context} aria-label="Product">
          <span className={styles.mark} aria-hidden="true">
            <Icon name="spark" />
          </span>
          <p className={styles.product}>Smart RAG</p>
          <p className={styles.contextCopy}>
            Grounded answers from your company&apos;s knowledge.
          </p>
        </aside>
        <div className={styles.formColumn}>
          <div className={styles.mobileBrand}>
            <span className={styles.mark} aria-hidden="true">
              <Icon name="spark" />
            </span>
            <p className={styles.product}>Smart RAG</p>
          </div>
          <main id="main" className={styles.main} tabIndex={-1}>
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
