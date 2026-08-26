/**
 * Command palette for supported console routes plus Sign out.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { fetchMe } from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { sessionQueryKeys } from "../../lib/query-keys";
import { commandDestinations } from "../../lib/shell-navigation";
import { Button } from "./button";
import { Icon } from "./icon";
import styles from "./ui.module.css";

export type CommandMenuProps = {
  /** Whether the dialog is open. */
  open: boolean;
  /** Close handler. */
  onClose: () => void;
};

/**
 * Render the console command dialog.
 *
 * @param props - Open flag and close handler.
 * @returns Dialog or null. Side effects: route push or Auth sign-out.
 */
export function CommandMenu({ open, onClose }: CommandMenuProps) {
  const router = useRouter();
  const session = useSession();
  const token = session.accessToken;
  const auth = token === null ? null : { accessToken: token };
  const meQuery = useQuery({
    queryKey: sessionQueryKeys(token).me,
    queryFn: () => fetchMe(auth!),
    enabled: auth !== null,
  });
  const destinations = commandDestinations(meQuery.data?.role);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === "") {
      return destinations;
    }
    return destinations.filter((item) => item.label.toLowerCase().includes(needle));
  }, [destinations, query]);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
    }
  }, [open]);

  if (!open) {
    return null;
  }

  const signOutIndex = matches.length;

  /**
   * Arrow keys move; Enter activates; Escape closes.
   *
   * @param event - Input keyboard event.
   */
  function onInputKeyDown(event: ReactKeyboardEvent<HTMLInputElement>): void {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((value) => Math.min(value + 1, signOutIndex));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((value) => Math.max(value - 1, 0));
      return;
    }
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    if (active === signOutIndex) {
      void session.signOut();
      onClose();
      return;
    }
    const item = matches[active];
    if (item === undefined) {
      return;
    }
    router.push(item.href);
    onClose();
  }

  return (
    <div className={styles.commandRoot} data-action-id="shell.command">
      <button
        type="button"
        className={styles.commandBackdrop}
        aria-label="Close command menu"
        onClick={onClose}
      />
      <div
        className={styles.commandPanel}
        role="dialog"
        aria-modal="true"
        aria-label="Go to"
      >
        <label className={styles.field} htmlFor="command-menu-query">
          Filter pages
          <input
            ref={inputRef}
            id="command-menu-query"
            className={styles.control}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            onKeyDown={onInputKeyDown}
            autoComplete="off"
          />
        </label>
        <ul className={styles.commandList}>
          {matches.map((item, index) => (
            <li key={item.href}>
              <Button
                type="button"
                variant="ghost"
                data-action-id={item.actionId}
                aria-current={index === active ? "true" : undefined}
                onClick={() => {
                  router.push(item.href);
                  onClose();
                }}
              >
                <Icon name={item.icon} />
                {item.label}
              </Button>
            </li>
          ))}
          <li>
            <Button
              type="button"
              variant="ghost"
              data-action-id="account.sign_out"
              data-testid="command-sign-out"
              aria-current={active === signOutIndex ? "true" : undefined}
              onClick={() => {
                void session.signOut();
                onClose();
              }}
            >
              <Icon name="logout" />
              Sign out
            </Button>
          </li>
        </ul>
      </div>
    </div>
  );
}

/**
 * Subscribe to Ctrl/Cmd+K for the command dialog.
 *
 * @param onOpen - Open handler.
 * @returns Cleanup.
 */
export function useCommandMenuShortcut(onOpen: () => void): void {
  useEffect(() => {
    /**
     * Open on Ctrl/Cmd+K.
     *
     * @param event - Window keyboard event.
     */
    function onKeyDown(event: KeyboardEvent): void {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpen();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onOpen]);
}
