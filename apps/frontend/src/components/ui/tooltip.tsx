/**
 * Hover/focus tooltip. Short description only; never required instructions.
 */

"use client";

import { useId, useState, type ReactNode } from "react";
import styles from "./styles/overlays.module.css";

export type TooltipProps = {
  /** Short descriptive text. */
  text: string;
  /** Trigger that receives hover and focus. */
  children: ReactNode;
};

/**
 * Wrap a control with an `aria-describedby` tooltip.
 *
 * @param props - Tooltip text and trigger.
 * @returns Wrapper that shows the tooltip on hover and keyboard focus.
 */
export function Tooltip({ text, children }: TooltipProps) {
  const tooltipId = useId();
  const [visible, setVisible] = useState(false);
  return (
    <span
      className={styles.overlayAnchor}
      onMouseEnter={() => {
        setVisible(true);
      }}
      onMouseLeave={() => {
        setVisible(false);
      }}
      onFocus={() => {
        setVisible(true);
      }}
      onBlur={() => {
        setVisible(false);
      }}
    >
      <span aria-describedby={visible ? tooltipId : undefined}>{children}</span>
      {visible ? (
        <span id={tooltipId} role="tooltip" className={styles.tooltipPanel}>
          {text}
        </span>
      ) : null}
    </span>
  );
}
