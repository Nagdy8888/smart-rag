/**
 * Modal drawer with Escape-to-close, focus trap, and restore-trigger.
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
import styles from "./ui.module.css";

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export type DrawerProps = {
  /** Accessible title. */
  title: string;
  /** Close handler. Escape and the Close button call this. */
  onClose: () => void;
  /** Drawer body. */
  children: ReactNode;
  /** Element that opened the drawer; focus returns here. */
  returnFocusRef?: RefObject<HTMLElement | null>;
};

/**
 * List currently focusable elements inside a container.
 *
 * @param root - Drawer node.
 * @returns Focusable HTMLElements in DOM order.
 */
function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (node) => !node.hasAttribute("disabled"),
  );
}

/**
 * Render a dialog with a simple focus trap.
 *
 * @param props - Title, close handler, optional return-focus ref.
 * @returns `role="dialog"` aside.
 * @remarks
 * Side effects: focuses the first control on mount and restores the
 * trigger on unmount. Escape closes. Tab cycles inside the drawer.
 */
export function Drawer({ title, onClose, children, returnFocusRef }: DrawerProps) {
  const containerRef = useRef<HTMLElement>(null);
  const titleId = useId();

  useEffect(() => {
    const previouslyFocused = returnFocusRef?.current ?? null;
    const root = containerRef.current;
    const first = root ? focusableElements(root)[0] : undefined;
    first?.focus();
    return () => {
      previouslyFocused?.focus();
    };
  }, [returnFocusRef]);

  /**
   * Trap Tab and handle Escape.
   *
   * @param event - Keyboard event from the dialog.
   */
  function onKeyDown(event: KeyboardEvent<HTMLElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab" || containerRef.current === null) {
      return;
    }
    const nodes = focusableElements(containerRef.current);
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
    <aside
      ref={containerRef}
      className={styles.drawer}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onKeyDown={onKeyDown}
    >
      <div className={styles.drawerHeader}>
        <h3 id={titleId}>{title}</h3>
        <Button type="button" onClick={onClose}>
          Close
        </Button>
      </div>
      {children}
    </aside>
  );
}
