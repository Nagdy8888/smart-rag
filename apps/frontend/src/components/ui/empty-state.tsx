/**
 * Empty collection or transcript placeholder. Never fakes a successful result.
 */

import type { ReactNode } from "react";
import styles from "./ui.module.css";

export type EmptyStateProps = {
  /** English heading for the empty region. */
  title: string;
  /** Optional supporting copy or actions. */
  children?: ReactNode;
};

/**
 * Render a dashed empty-state panel.
 *
 * @param props - Title and optional body.
 * @returns Non-alert placeholder. No fetch side effects.
 */
export function EmptyState({ title, children }: EmptyStateProps) {
  return (
    <div className={styles.emptyState}>
      <p>
        <strong>{title}</strong>
      </p>
      {children}
    </div>
  );
}
