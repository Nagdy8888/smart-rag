/**
 * Modal confirmation. Focus trap, Escape, and pending lock.
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

export type ConfirmDialogProps = {
  /** Dialog title. */
  title: string;
  /** Consequence copy. Must name the object for destructive actions. */
  children: ReactNode;
  /** Close handler. Ignored while pending. */
  onClose: () => void;
  /** Confirm handler. */
  onConfirm: () => void;
  /** Confirm label. */
  confirmLabel: string;
  /** Pending confirm label. */
  pendingLabel?: string;
  /** When true, confirm is danger and initial focus is Cancel. */
  danger?: boolean;
  /** Blocks dismiss and duplicate confirm. */
  pending?: boolean;
  /** Trigger to restore. */
  returnFocusRef?: RefObject<HTMLElement | null>;
};

/**
 * List currently focusable elements inside a container.
 *
 * @param root - Dialog node.
 * @returns Focusable HTMLElements in DOM order.
 */
function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (node) => !node.hasAttribute("disabled"),
  );
}

/**
 * Render a centered confirmation dialog.
 *
 * @param props - Title, body, confirm/cancel, pending lock.
 * @returns Modal dialog. Side effects: focus trap and restore.
 */
export function ConfirmDialog({
  title,
  children,
  onClose,
  onConfirm,
  confirmLabel,
  pendingLabel,
  danger = false,
  pending = false,
  returnFocusRef,
}: ConfirmDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  useEffect(() => {
    const previouslyFocused =
      returnFocusRef?.current ?? (document.activeElement as HTMLElement | null);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (danger) {
      cancelRef.current?.focus();
    } else {
      const root = panelRef.current;
      const first = root ? focusableElements(root)[0] : undefined;
      first?.focus();
    }
    return () => {
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus();
    };
  }, [danger, returnFocusRef]);

  /**
   * Trap Tab and handle Escape when no irreversible request is pending.
   *
   * @param event - Keyboard event from the dialog.
   */
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      if (!pending) {
        onClose();
      }
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
    <div className={styles.confirmRoot}>
      <div
        className={styles.confirmBackdrop}
        aria-hidden="true"
        onClick={() => {
          if (!pending) {
            onClose();
          }
        }}
      />
      <div
        ref={panelRef}
        className={styles.confirmPanel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
      >
        <h2 id={titleId} className={styles.confirmTitle}>
          {title}
        </h2>
        <div className={styles.confirmBody}>{children}</div>
        <div className={styles.confirmActions}>
          <Button ref={cancelRef} type="button" disabled={pending} onClick={() => { if (!pending) onClose(); }}>
            Cancel
          </Button>
          <Button
            type="button"
            variant={danger ? "danger" : "primary"}
            pending={pending}
            pendingLabel={pendingLabel ?? "Working…"}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
