/**
 * Left-aligned empty-state text with an optional muted icon. Never fakes a successful result.
 */

import type { ReactNode } from "react";
import { Icon, type IconName } from "./icon";
import styles from "./styles/data-display.module.css";

export type EmptyStateProps = {
  /** English heading for the empty region. */
  title: string;
  /** One supporting body line. */
  body?: string;
  /** Optional small muted Lucide icon shown before the title. */
  icon?: IconName;
  /** Optional primary action row. */
  action?: ReactNode;
  /** Extra content such as prompt lists. */
  children?: ReactNode;
};

/**
 * Render a borderless, left-aligned empty state.
 *
 * @param props - Title, optional body, icon, action, and extra children.
 * @returns Non-alert placeholder. No fetch side effects.
 * @remarks
 * The container that holds it owns any border. Never nest it inside a card.
 */
export function EmptyState({
  title,
  body,
  icon,
  action,
  children,
}: EmptyStateProps) {
  return (
    <div className={styles.emptyState}>
      <h3 className={styles.emptyStateTitle}>
        {icon ? (
          <span className={styles.emptyStateIcon} aria-hidden="true">
            <Icon name={icon} />
          </span>
        ) : null}
        {title}
      </h3>
      {body ? <p className={styles.emptyStateBody}>{body}</p> : null}
      {action ? <div className={styles.emptyStateActions}>{action}</div> : null}
      {children}
    </div>
  );
}
