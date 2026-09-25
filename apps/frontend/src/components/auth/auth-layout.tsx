/**
 * Focused public Auth layout. No console navigation.
 */

import type { ReactNode } from "react";
import styles from "./auth.module.css";

export type AuthLayoutProps = {
  /** Auth card or unavailable body. */
  children: ReactNode;
};

/**
 * Render the public Auth layout: product header, centered form column, and footer.
 *
 * @param props - Route children.
 * @returns Skip link, product header, `#main` landmark, and footer.
 * @remarks
 * URLs stay `/login` and siblings. Proxy/session behavior is unchanged.
 */
export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className={styles.page}>
      <a className={styles.skipLink} href="#main" data-action-id="shell.skip">
        Skip to main content
      </a>
      <header className={styles.header}>
        <span className={styles.mark} aria-hidden="true">
          SR
        </span>
        <p className={styles.product}>Smart RAG</p>
      </header>
      <div className={styles.formColumn}>
        <main id="main" className={styles.main} tabIndex={-1}>
          {children}
        </main>
      </div>
      <footer className={styles.footer}>
        <p>Answers cite the company documents they come from.</p>
      </footer>
    </div>
  );
}
