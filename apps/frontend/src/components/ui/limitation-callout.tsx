/**
 * Signed limitation callout. BM25 degradation stays warning, not danger.
 */

import type { ReactNode } from "react";
import { displayText } from "../../lib/safe-text";
import styles from "./ui.module.css";

export type LimitationCalloutProps = {
  /** Signed copy or React nodes already passed through `displayText`. */
  children: ReactNode;
  /** Visual tone. Default `warning` for non-alarming degradation. */
  tone?: "warning" | "neutral" | "danger";
};

/**
 * Render a limitation sentence as `role="status"`.
 *
 * @param props - Signed copy. Do not invent bypass language.
 * @returns Status region. No fetch side effects.
 */
export function LimitationCallout({
  children,
  tone = "warning",
}: LimitationCalloutProps) {
  const toneClass =
    tone === "warning"
      ? styles.calloutWarning
      : tone === "danger"
        ? styles.bannerError
        : undefined;
  const combined = [styles.callout, toneClass].filter(Boolean).join(" ");
  const body = typeof children === "string" ? displayText(children) : children;
  return (
    <p className={combined} role="status">
      {body}
    </p>
  );
}
