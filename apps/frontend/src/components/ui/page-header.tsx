/**
 * Single page title region. Feature packets compose this; this packet does not
 * change routes.
 */

import type { ReactNode } from "react";
import styles from "./ui.module.css";

export type PageHeaderProps = {
  /**
   * Ignored. The console topbar owns the single page title.
   * Accepted so existing call sites can drop the heading without an extra PR.
   */
  title?: string;
  /** Optional supporting sentence under the topbar. */
  description?: string;
  /** At most one primary action plus overflow. */
  actions?: ReactNode;
};

/**
 * Render the page lead and actions. The topbar owns the page title.
 *
 * @param props - Optional description and actions. `title` is not rendered.
 * @returns Header landmark contents, or null when there is nothing to show.
 */
export function PageHeader({ description, actions }: PageHeaderProps) {
  if (!description && !actions) {
    return null;
  }
  return (
    <header className={styles.pageHeader}>
      <div className={styles.pageHeaderCopy}>
        {description ? (
          <p className={styles.pageHeaderDescription}>{description}</p>
        ) : null}
      </div>
      {actions ? <div className={styles.pageHeaderActions}>{actions}</div> : null}
    </header>
  );
}
