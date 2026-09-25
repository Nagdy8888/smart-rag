/**
 * Hover/focus tooltip. Short description only; never required instructions.
 */

"use client";

import { useId, useRef, useState, type CSSProperties, type ReactNode } from "react";
import styles from "./styles/overlays.module.css";

export type TooltipPlacement = "bottom" | "end";

export type TooltipProps = {
  /** Short descriptive text. */
  text: string;
  /** Trigger that receives hover and focus. */
  children: ReactNode;
  /**
   * `end` uses a viewport-fixed panel to the right of the trigger so
   * collapsed nav-rail labels are not clipped by `overflow: auto`.
   */
  placement?: TooltipPlacement;
};

/**
 * Wrap a control with an `aria-describedby` tooltip.
 *
 * @param props - Tooltip text, trigger, and optional placement.
 * @returns Wrapper that shows the tooltip on hover and keyboard focus.
 */
export function Tooltip({
  text,
  children,
  placement = "bottom",
}: TooltipProps) {
  const tooltipId = useId();
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(
    null,
  );
  const anchorRef = useRef<HTMLSpanElement>(null);

  /**
   * Show the tooltip and, for `end` placement, pin it beside the trigger.
   */
  function show(): void {
    setVisible(true);
    if (placement === "end" && anchorRef.current !== null) {
      const box = anchorRef.current.getBoundingClientRect();
      setCoords({ top: box.top + box.height / 2, left: box.right + 8 });
    }
  }

  const endStyle: CSSProperties | undefined =
    placement === "end" && coords !== null
      ? { top: coords.top, left: coords.left }
      : undefined;

  return (
    <span
      ref={anchorRef}
      className={styles.overlayAnchor}
      onMouseEnter={show}
      onMouseLeave={() => {
        setVisible(false);
      }}
      onFocus={show}
      onBlur={() => {
        setVisible(false);
      }}
    >
      <span aria-describedby={visible ? tooltipId : undefined}>{children}</span>
      {visible ? (
        <span
          id={tooltipId}
          role="tooltip"
          className={
            placement === "end"
              ? `${styles.tooltipPanel} ${styles.tooltipPanelEnd}`
              : styles.tooltipPanel
          }
          style={endStyle}
        >
          {text}
        </span>
      ) : null}
    </span>
  );
}
