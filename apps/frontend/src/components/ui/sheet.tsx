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
import { lockBodyScroll } from "./body-scroll-lock";
import { Button } from "./button";
import { trapFocus } from "./focus-trap";
import { Icon } from "./icon";
import overlayStyles from "./styles/overlays.module.css";
import leftoverStyles from "./ui.module.css";

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
  /** Extra class on the panel. Width and surface only. */
  panelClassName?: string;
};

/**
 * Render a modal side panel.
 *
 * @param props - Title, close handler, optional side, panel class, and return-focus ref.
 * @returns Dialog overlay. Side effects: focus trap, body scroll lock, restore.
 */
export function Sheet({
  title,
  onClose,
  children,
  side = "right",
  returnFocusRef,
  panelClassName,
}: SheetProps) {
  const panelRef = useRef<HTMLDivElement>(null);
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
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  }

  return (
    <div className={overlayStyles.sheetRoot}>
      <button
        type="button"
        className={overlayStyles.sheetBackdrop}
        aria-label="Close"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        className={[
          side === "left" ? overlayStyles.sheetPanelLeft : overlayStyles.sheetPanelRight,
          panelClassName,
        ]
          .filter(Boolean)
          .join(" ")}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKeyDown}
      >
        <div className={overlayStyles.sheetHeader}>
          <h2 id={titleId}>{title}</h2>
          <Button type="button" variant="ghost" size="icon" onClick={onClose} aria-label="Close">
            <Icon name="close" />
            <span className={leftoverStyles.srOnly}>Close</span>
          </Button>
        </div>
        <div className={overlayStyles.sheetBody}>{children}</div>
      </div>
    </div>
  );
}
