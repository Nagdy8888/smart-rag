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
import { lockBodyScroll } from "./body-scroll-lock";
import { Button } from "./button";
import { trapFocus } from "./focus-trap";
import styles from "./styles/overlays.module.css";

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
 * Render a centered confirmation dialog.
 *
 * @param props - Title, body, confirm/cancel, pending lock.
 * @returns Modal dialog. Side effects: focus trap, scroll lock, and restore.
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
    const root = panelRef.current;
    if (root === null) {
      return;
    }
    const unlock = lockBodyScroll();
    const release = trapFocus(root, {
      returnFocus:
        returnFocusRef?.current ?? (document.activeElement as HTMLElement | null),
      initialFocus: danger ? cancelRef.current : undefined,
    });
    return () => {
      release();
      unlock();
    };
  }, [danger, returnFocusRef]);

  /**
   * Close on Escape when no irreversible request is pending.
   *
   * @param event - Keyboard event from the dialog.
   */
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      if (!pending) {
        onClose();
      }
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
          <Button
            ref={cancelRef}
            type="button"
            disabled={pending}
            onClick={() => {
              if (!pending) onClose();
            }}
          >
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
