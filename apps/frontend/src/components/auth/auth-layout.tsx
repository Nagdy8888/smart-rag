/** Public authentication shell with a focused form and evidence introduction. */
import type { ReactNode } from "react";
import { Icon } from "../ui/icon";
import styles from "./auth.module.css";
import entry from "./auth-entry.module.css";

export type AuthLayoutProps = {
  /** Auth card or unavailable body. */
  children: ReactNode;
};

/** Keep public authentication separate from the signed-in console. */
export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className={entry.page}>
      <a className={styles.skipLink} href="#main" data-action-id="shell.skip">Skip to main content</a>
      <aside className={entry.introduction} aria-label="About Smart RAG">
        <header className={entry.brand}>
          <span className={entry.brandMark} aria-hidden="true"><Icon name="documents" /></span>
          <span>Smart RAG</span>
        </header>
        <div className={entry.story}>
          <h2>Go straight to the evidence.</h2>
          <p>A workspace for asking better questions and finding the passages behind the answers.</p>
          <ul className={entry.workflow}>
            <li><Icon name="chat" /><div><strong>Ask in your own words</strong><span>Explore the knowledge in your company documents.</span></div></li>
            <li><Icon name="documents" /><div><strong>Read with context</strong><span>Follow explanations, tables, code, and original figures.</span></div></li>
            <li><Icon name="search" /><div><strong>See where it came from</strong><span>Open citations on the original page, with matching text highlighted.</span></div></li>
          </ul>
        </div>
        <p className={entry.brandNote}>Your question. Your documents. The original source.</p>
      </aside>
      <section className={entry.formSection} aria-label="Account access">
        <main id="main" className={entry.main} tabIndex={-1}>{children}</main>
        <footer className={entry.footer}>Company answers link back to their sources.</footer>
      </section>
    </div>
  );
}
