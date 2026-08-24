/**
 * Modal side sheet: focus trap, Escape, scroll lock, restore trigger.
 */

"use client";

import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { Button } from "./button";
import { Icon } from "./icon";
import styles from "./ui.module.css";

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export type SheetSide = "left" | "right";

export type SheetProps = {
  /** Accessible title. */
  title: string;
  /** Close handler. Escape, backdrop, and Close call this. */
  onClose: () => void;
  /** Sheet body. */
  children: ReactNode;
  /** Which edge the panel attaches to. Default `right`. */
  side?: SheetSide;
  /** Element that opened the sheet; focus returns here. */
  returnFocusRef?: RefObject<HTMLElement | null>;
};

/**
 * List currently focusable elements inside a container.
 *
 * @param root - Sheet node.
 * @returns Focusable HTMLElements in DOM order.
 */
function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (node) => !node.hasAttribute("disabled"),
  );
}

/**
 * Render a modal side panel.
 *
 * @param props - Title, close handler, optional side and return-focus ref.
 * @returns Dialog overlay. Side effects: focus trap, body scroll lock, restore.
 */
export function Sheet({
  title,
  onClose,
  children,
  side = "right",
  returnFocusRef,
}: SheetProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    const previouslyFocused = returnFocusRef?.current ?? (document.activeElement as HTMLElement | null);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const root = panelRef.current;
    const first = root ? focusableElements(root)[0] : undefined;
    first?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [returnFocusRef]);

  /**
   * Trap Tab and handle Escape.
   *
   * @param event - Keyboard event from the dialog.
   */
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab" || panelRef.current === null) {
      return;
    }
    const nodes = focusableElements(panelRef.current);
    if (nodes.length === 0) {
      return;
    }
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (first === undefined || last === undefined) {
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
      return;
    }
    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div className={styles.sheetRoot}>
      <button
        type="button"
        className={styles.sheetBackdrop}
        aria-label="Close"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        className={side === "left" ? styles.sheetPanelLeft : styles.sheetPanelRight}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
      >
        <div className={styles.sheetHeader}>
          <h2 id={titleId}>{title}</h2>
          <Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <Icon name="close" />
            <span className={styles.srOnly}>Close</span>
          </Button>
        </div>
        <div className={styles.sheetBody}>{children}</div>
      </div>
    </div>
  );
}
