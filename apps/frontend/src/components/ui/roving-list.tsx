/**
 * Roving tabindex list for conversation and document collections.
 */

"use client";

import {
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import styles from "./ui.module.css";

export type RovingListItem<T> = {
  /** Stable id used as React key and option identity. */
  id: string;
  /** Row payload. */
  item: T;
};

export type RovingListProps<T> = {
  /** Accessible name for the listbox. */
  "aria-label": string;
  /** Rows. */
  items: Array<RovingListItem<T>>;
  /** Currently selected id, when any. */
  selectedId?: string | null;
  /** Activate a row (click or Enter/Space). */
  onSelect: (item: T) => void;
  /** Row contents. Must be text-safe. */
  children: (item: T) => ReactNode;
  /** Optional extra class on the list. */
  className?: string;
  /** Override the option accessible name when the row has nested controls. */
  getAccessibleName?: (item: T) => string;
};

/**
 * Render a single-tab-stop listbox with arrow-key movement.
 *
 * @param props - Items, selection, and row renderer.
 * @returns `role="listbox"` list.
 * @remarks
 * ArrowUp/ArrowDown/Home/End move the roving tabindex. Enter/Space select.
 */
export function RovingList<T>({
  "aria-label": ariaLabel,
  items,
  selectedId = null,
  onSelect,
  children,
  className,
  getAccessibleName,
}: RovingListProps<T>) {
  const [activeIndex, setActiveIndex] = useState(0);
  const buttonRefs = useRef<Array<HTMLElement | null>>([]);
  const active =
    items.length === 0 ? 0 : Math.min(activeIndex, items.length - 1);

  /**
   * Move the active option and focus it. Does not focus on first paint.
   *
   * @param next - Index to activate.
   */
  function moveTo(next: number): void {
    setActiveIndex(next);
    queueMicrotask(() => {
      buttonRefs.current[next]?.focus();
    });
  }

  /**
   * Move the active option without leaving the listbox.
   *
   * @param event - Keyboard event on the list.
   */
  function onKeyDown(event: KeyboardEvent<HTMLUListElement>): void {
    if (items.length === 0) {
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveTo(Math.min(items.length - 1, active + 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      moveTo(Math.max(0, active - 1));
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      moveTo(0);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      moveTo(items.length - 1);
    }
  }

  return (
    <ul
      className={[styles.rovingList, className].filter(Boolean).join(" ")}
      role="listbox"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
    >
      {items.map((row, index) => {
        const selected = row.id === selectedId;
        return (
          <li key={row.id} role="presentation">
            <div
              role="option"
              aria-selected={selected}
              aria-label={getAccessibleName?.(row.item)}
              tabIndex={index === active ? 0 : -1}
              ref={(node) => {
                buttonRefs.current[index] = node;
              }}
              onClick={() => onSelect(row.item)}
              onFocus={() => setActiveIndex(index)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(row.item);
                }
              }}
            >
              {children(row.item)}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
