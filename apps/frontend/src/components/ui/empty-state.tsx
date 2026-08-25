/**
 * Centered empty collection or transcript placeholder.
 *
 * Never fakes a successful result. The brand gradient tile is an approved
 * brand-moment exception from the no-gradient-on-controls rule.
 */

import type { ReactNode } from "react";
import { Icon, type IconName } from "./icon";
import styles from "./ui.module.css";

export type EmptyStateProps = {
  /** English heading for the empty region. */
  title: string;
  /** One supporting body line. */
  body?: string;
  /** Lucide icon in the brand tile. Default `spark`. */
  icon?: IconName;
  /** Optional primary action row. */
  action?: ReactNode;
  /** Extra content such as prompt chips. */
  children?: ReactNode;
};

/**
 * Render a centered empty-state panel with a brand icon tile.
 *
 * @param props - Title, optional body, icon, action, and extra children.
 * @returns Non-alert placeholder. No fetch side effects.
 */
export function EmptyState({
  title,
  body,
  icon = "spark",
  action,
  children,
}: EmptyStateProps) {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyStateTile} aria-hidden="true">
        <Icon name={icon} />
      </div>
      <h3 className={styles.emptyStateTitle}>{title}</h3>
      {body ? <p className={styles.emptyStateBody}>{body}</p> : null}
      {action ? <div className={styles.emptyStateActions}>{action}</div> : null}
      {children}
    </div>
  );
}
