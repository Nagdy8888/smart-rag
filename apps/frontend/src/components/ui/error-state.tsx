/**
 * Generic error state. Production copy stays non-technical.
 */

import type { ReactNode } from "react";
import { displayText } from "../../lib/safe-text";
import styles from "./ui.module.css";

export type ErrorStateProps = {
  /** English title. */
  title: string;
  /** Untrusted or generic detail. */
  message: unknown;
  /** Optional extra actions. */
  children?: ReactNode;
};

/**
 * Render a blocking error region.
 *
 * @param props - Title, message, optional actions.
 * @returns `role="alert"` container. Does not retry by itself.
 */
export function ErrorState({ title, message, children }: ErrorStateProps) {
  return (
    <div className={styles.errorState} role="alert">
      <p>
        <strong>{title}</strong>
      </p>
      <p>{displayText(message)}</p>
      {children}
    </div>
  );
}
