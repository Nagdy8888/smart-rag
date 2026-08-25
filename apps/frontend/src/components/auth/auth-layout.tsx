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
 * Render a light split Auth composition: product context plus form surface.
 *
 * @param props - Route children.
 * @returns Skip link, restrained brand context, and `#main` landmark.
 * @remarks
 * URLs stay `/login` and siblings. Proxy/session behavior is unchanged.
 * No readiness dashboard, testimonials, gradients, or console nav.
 * Form fields and Auth callbacks remain in `auth-screens.tsx`.
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
          <p className={styles.subbrand}>Evidence workspace for company knowledge</p>
          <p className={styles.contextCopy}>
            Ask grounded questions, inspect sources, and manage ingestion without
            leaving the signed-in console.
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
