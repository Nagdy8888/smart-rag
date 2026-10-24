/**
 * Anchored action menu. Keyboard list, Escape, outside click, focus restore.
 *
 * The panel is portaled to `document.body` with `position: fixed` so table
 * `overflow: auto` wrappers cannot clip it.
 */

"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
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
  /** Non-interactive profile or context above the action rows. */
  header?: ReactNode;
  panelClassName?: string;
};

const VIEWPORT_MARGIN_PX = 8;
const TRIGGER_GAP_PX = 4;

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
 * Place a fixed menu against a trigger, right-aligned, clamped to the viewport.
 *
 * @param trigger - Trigger button.
 * @param panel - Portaled menu panel.
 * @returns CSS top/left in viewport pixels.
 */
function menuFixedPosition(
  trigger: HTMLElement,
  panel: HTMLElement,
): { top: number; left: number } {
  const rect = trigger.getBoundingClientRect();
  const width = panel.offsetWidth;
  const height = panel.offsetHeight;
  let left = rect.right - width;
  left = Math.min(left, window.innerWidth - width - VIEWPORT_MARGIN_PX);
  left = Math.max(VIEWPORT_MARGIN_PX, left);
  let top = rect.bottom + TRIGGER_GAP_PX;
  if (top + height > window.innerHeight - VIEWPORT_MARGIN_PX) {
    top = Math.max(VIEWPORT_MARGIN_PX, rect.top - height - TRIGGER_GAP_PX);
  }
  return { top, left };
}

/**
 * Render a trigger plus anchored menu list.
 *
 * @param props - Label, trigger node, and items.
 * @returns Menu widget. Side effects: focus restore on close.
 */
export function Menu({ label, trigger, items, triggerActionId, header, panelClassName }: MenuProps) {
  const [open, setOpen] = useState(false);
  const [measuredCoords, setMeasuredCoords] = useState<{
    top: number;
    left: number;
  } | null>(null);
  const coords = open ? measuredCoords : null;
  const wrapRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useLayoutEffect(() => {
    if (!open) {
      return;
    }
    /**
     * Recompute fixed coordinates after layout, scroll, or resize.
     */
    function updatePosition(): void {
      const triggerNode = triggerRef.current;
      const panelNode = panelRef.current;
      if (triggerNode === null || panelNode === null) {
        return;
      }
      const rect = triggerNode.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > window.innerHeight) {
        setOpen(false);
        return;
      }
      setMeasuredCoords(menuFixedPosition(triggerNode, panelNode));
    }
    updatePosition();
    enabledMenuItems(panelRef.current)[0]?.focus();
    window.addEventListener("resize", updatePosition);
    document.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      document.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    /**
     * Close on outside pointer down.
     *
     * @param event - Document pointer event.
     */
    function onPointerDown(event: PointerEvent): void {
      const target = event.target as Node;
      if (
        wrapRef.current?.contains(target) === true ||
        panelRef.current?.contains(target) === true
      ) {
        return;
      }
      setOpen(false);
      triggerRef.current?.focus();
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
    const buttons = enabledMenuItems(panelRef.current);
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

  const panelStyle: CSSProperties = coords
    ? { top: coords.top, left: coords.left }
    : { top: 0, left: 0, visibility: "hidden" };

  const panel =
    open && typeof document !== "undefined"
      ? createPortal(
          <div
            id={menuId}
            ref={panelRef}
            className={[styles.menuPanel, styles.menuPanelFixed, panelClassName].filter(Boolean).join(" ")}
            role="menu"
            aria-label={label}
            style={panelStyle}
            onKeyDown={onMenuKeyDown}
          >
            {header ? <div role="presentation">{header}</div> : null}
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
          </div>,
          document.body,
        )
      : null;

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
      {panel}
    </div>
  );
}
