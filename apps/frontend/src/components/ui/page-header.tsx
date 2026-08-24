/**
 * Single page title region. Feature packets compose this; this packet does not
 * change routes.
 */

import type { ReactNode } from "react";
import styles from "./ui.module.css";

export type PageHeaderProps = {
  /** Visible page title. One per page. */
  title: string;
  /** Optional supporting sentence. */
  description?: string;
  /** At most one primary action plus overflow. */
  actions?: ReactNode;
};

/**
 * Render the page heading block.
 *
 * @param props - Title, optional description and actions.
 * @returns Header landmark contents. No data fetching.
 */
export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <header className={styles.pageHeader}>
      <div className={styles.pageHeaderCopy}>
        <h1 className={styles.pageHeaderTitle}>{title}</h1>
        {description ? (
          <p className={styles.pageHeaderDescription}>{description}</p>
        ) : null}
      </div>
      {actions ? <div className={styles.pageHeaderActions}>{actions}</div> : null}
    </header>
  );
}
