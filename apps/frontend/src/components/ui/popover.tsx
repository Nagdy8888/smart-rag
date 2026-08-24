/**
 * Non-modal popover. Escape and outside click close; focus returns to trigger.
 * Must not contain destructive confirmations.
 */

"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button } from "./button";
import styles from "./ui.module.css";

export type PopoverProps = {
  /** Accessible name for the trigger. */
  label: string;
  /** Trigger contents. */
  trigger: ReactNode;
  /** Popover body. */
  children: ReactNode;
};

/**
 * Render a small non-modal disclosure.
 *
 * @param props - Label, trigger, and body.
 * @returns Popover widget. Side effects: focus restore on close.
 */
export function Popover({ label, trigger, children }: PopoverProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) {
      return;
    }
    /**
     * Close on outside pointer or Escape.
     *
     * @param event - Browser event.
     */
    function onPointerDown(event: PointerEvent): void {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    /**
     * Close on Escape from anywhere.
     *
     * @param event - Keyboard event.
     */
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className={styles.overlayAnchor} ref={wrapRef}>
      <Button
        ref={triggerRef}
        type="button"
        variant="ghost"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={label}
        onClick={() => {
          setOpen((value) => !value);
        }}
      >
        {trigger}
      </Button>
      {open ? (
        <div id={panelId} className={styles.popoverPanel} role="region" aria-label={label}>
          {children}
        </div>
      ) : null}
    </div>
  );
}
