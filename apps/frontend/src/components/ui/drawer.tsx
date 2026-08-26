/**
 * Modal drawer with backdrop, Escape, focus trap, scroll lock, and restore.
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
import { lockBodyScroll } from "./body-scroll-lock";
import { Button } from "./button";
import { trapFocus } from "./focus-trap";
import styles from "./styles/overlays.module.css";

export type DrawerProps = {
  /** Accessible title. */
  title: string;
  /** Close handler. Escape, backdrop, and Close call this. */
  onClose: () => void;
  /** Drawer body. */
  children: ReactNode;
  /** Element that opened the drawer; focus returns here. */
  returnFocusRef?: RefObject<HTMLElement | null>;
};

/**
 * Render a dialog with a visible backdrop and a simple focus trap.
 *
 * @param props - Title, close handler, optional return-focus ref.
 * @returns Overlay dialog. Side effects: scroll lock, trap, restore.
 * @remarks
 * Backdrop click and Escape close. Tab cycles inside the panel. Body scroll
 * is locked while mounted and released exactly once on unmount.
 */
export function Drawer({ title, onClose, children, returnFocusRef }: DrawerProps) {
  const containerRef = useRef<HTMLElement>(null);
  const titleId = useId();

  useEffect(() => {
    const root = containerRef.current;
    if (root === null) {
      return;
    }
    const unlock = lockBodyScroll();
    const release = trapFocus(root, {
      returnFocus: returnFocusRef?.current ?? null,
    });
    return () => {
      release();
      unlock();
    };
  }, [returnFocusRef]);

  /**
   * Close on Escape. Tab wrap lives in `trapFocus`.
   *
   * @param event - Keyboard event from the dialog.
   */
  function onKeyDown(event: KeyboardEvent<HTMLElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  }

  return (
    <div className={styles.drawerRoot}>
      <button
        type="button"
        className={styles.drawerBackdrop}
        aria-label="Dismiss drawer"
        onClick={onClose}
      />
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
    </div>
  );
}
