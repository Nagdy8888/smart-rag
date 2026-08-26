/**
 * Anchored action menu. Keyboard list, Escape, outside click, focus restore.
 */

"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Button } from "./button";
import { getFocusableElements } from "./focus-trap";
import styles from "./styles/overlays.module.css";

export type MenuItem = {
  /** Stable item id. */
  id: string;
  /** Visible English label. */
  label: ReactNode;
  /** Invoked when the item is chosen. */
  onSelect: () => void;
  /** Destructive styling. Confirmation still belongs to the caller. */
  danger?: boolean;
  /** Skip in arrow-key movement. */
  disabled?: boolean;
  /** Stable `data-action-id` when the row is an inventory action. */
  actionId?: string;
};

export type MenuProps = {
  /** Accessible name for the trigger. */
  label: string;
  /** Trigger contents. */
  trigger: ReactNode;
  /** Action rows. */
  items: readonly MenuItem[];
  /** Inventory id on the trigger button. */
  triggerActionId?: string;
};

/**
 * Enabled menuitem buttons inside the open panel.
 *
 * @param root - Menu wrap.
 * @returns Enabled menuitem buttons.
 */
function enabledMenuItems(root: HTMLElement | null): HTMLButtonElement[] {
  if (root === null) {
    return [];
  }
  return getFocusableElements(root).filter(
    (node): node is HTMLButtonElement =>
      node instanceof HTMLButtonElement && node.getAttribute("role") === "menuitem",
  );
}

/**
 * Render a trigger plus anchored menu list.
 *
 * @param props - Label, trigger node, and items.
 * @returns Menu widget. Side effects: focus restore on close.
 */
export function Menu({ label, trigger, items, triggerActionId }: MenuProps) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) {
      return;
    }
    enabledMenuItems(wrapRef.current)[0]?.focus();
    /**
     * Close on outside pointer down.
     *
     * @param event - Document pointer event.
     */
    function onPointerDown(event: PointerEvent): void {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open]);

  /**
   * Move among enabled items and handle Escape/Home/End.
   *
   * @param event - Keyboard event from the menu.
   */
  function onMenuKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
      return;
    }
    const buttons = enabledMenuItems(wrapRef.current);
    if (buttons.length === 0) {
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      buttons[0]?.focus();
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      buttons[buttons.length - 1]?.focus();
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
      return;
    }
    event.preventDefault();
    const current = buttons.findIndex((node) => node === document.activeElement);
    const delta = event.key === "ArrowDown" ? 1 : -1;
    const next = current < 0 ? 0 : (current + delta + buttons.length) % buttons.length;
    buttons[next]?.focus();
  }

  return (
    <div className={styles.overlayAnchor} ref={wrapRef}>
      <Button
        ref={triggerRef}
        type="button"
        variant="ghost"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={label}
        data-action-id={triggerActionId}
        onClick={() => {
          setOpen((value) => !value);
        }}
      >
        {trigger}
      </Button>
      {open ? (
        <div
          id={menuId}
          className={styles.menuPanel}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKeyDown}
        >
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              className={item.danger ? styles.menuItemDanger : styles.menuItem}
              disabled={item.disabled}
              data-action-id={item.actionId}
              onClick={() => {
                item.onSelect();
                setOpen(false);
                triggerRef.current?.focus();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
