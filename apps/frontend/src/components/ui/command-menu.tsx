/**
 * Command dialog for the nine console routes plus Sign out.
 * Not corpus search. Does not create data.
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useSession } from "../../lib/auth/session-provider";
import { Button } from "./button";
import { Icon } from "./icon";
import { Sheet } from "./sheet";
import styles from "./ui.module.css";

const COMMAND_ROUTES: ReadonlyArray<{ href: string; label: string }> = [
  { href: "/", label: "Ask" },
  { href: "/documents", label: "Documents" },
  { href: "/graph", label: "Graph" },
  { href: "/tables", label: "Tables" },
  { href: "/team", label: "Team" },
  { href: "/tools", label: "Tools" },
  { href: "/curation", label: "Curation" },
  { href: "/usage", label: "Usage" },
  { href: "/profile", label: "Profile" },
];

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
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === "") {
      return COMMAND_ROUTES;
    }
    return COMMAND_ROUTES.filter((item) => item.label.toLowerCase().includes(needle));
  }, [query]);

  if (!open) {
    if (query !== "") {
      setQuery("");
    }
    return null;
  }

  /**
   * Enter activates the first match.
   *
   * @param event - Input keyboard event.
   */
  function onInputKeyDown(event: ReactKeyboardEvent<HTMLInputElement>): void {
    if (event.key !== "Enter") {
      return;
    }
    const first = matches[0];
    if (first === undefined) {
      return;
    }
    event.preventDefault();
    router.push(first.href);
    onClose();
  }

  return (
    <Sheet title="Go to" onClose={onClose} side="right">
      <label className={styles.field} htmlFor="command-menu-query">
        Filter pages
        <input
          ref={inputRef}
          id="command-menu-query"
          className={styles.control}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
          onKeyDown={onInputKeyDown}
          autoComplete="off"
        />
      </label>
      <ul className={styles.commandList}>
        {matches.map((item) => (
          <li key={item.href}>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                router.push(item.href);
                onClose();
              }}
            >
              {item.label}
            </Button>
          </li>
        ))}
        <li>
          <Button
            type="button"
            variant="ghost"
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
    </Sheet>
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
