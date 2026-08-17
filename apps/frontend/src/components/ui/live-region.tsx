/**
 * Live region for stream tokens, reconnect, and terminal notices.
 */

import type { ReactNode } from "react";
import { displayText } from "../../lib/safe-text";
import styles from "./ui.module.css";

export type LiveRegionProps = {
  /** Live contents. Strings go through `displayText`. */
  children: ReactNode;
  /** Politeness. Use `assertive` only for blocking errors. */
  politeness?: "polite" | "assertive" | "off";
  /** Optional accessible name. */
  "aria-label"?: string;
};

/**
 * Render an `aria-live` region without HTML interpolation.
 *
 * @param props - Politeness and body.
 * @returns Div. Heartbeats should not be announced every 15s by callers.
 */
export function LiveRegion({
  children,
  politeness = "polite",
  "aria-label": ariaLabel,
}: LiveRegionProps) {
  const body = typeof children === "string" ? displayText(children) : children;
  return (
    <div className={styles.liveRegion} aria-live={politeness} aria-label={ariaLabel}>
      {body}
    </div>
  );
}
