/**
 * Compact status and category badge. Not an authorization signal.
 */

import type { HTMLAttributes } from "react";
import { UserText } from "./user-text";
import styles from "./ui.module.css";

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  /** Untrusted label. Rendered through `displayText`. */
  label: unknown;
};

/**
 * Render a compact label chip.
 *
 * @param props - Untrusted `label` plus optional className.
 * @returns Span. Visibility is not a permission check.
 */
export function Badge({ label, className, ...rest }: BadgeProps) {
  const combined = className ? `${styles.badge} ${className}` : styles.badge;
  return (
    <span className={combined} {...rest}>
      <UserText value={label} />
    </span>
  );
}
