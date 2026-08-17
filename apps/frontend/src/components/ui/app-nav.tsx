/**
 * Client nav so `aria-current` tracks the real pathname.
 * Nav is not authorization.
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./app-shell.module.css";

const NAV_ITEMS = [
  { href: "/", label: "Chat" },
  { href: "/documents", label: "Documents" },
  { href: "/graph", label: "Graph" },
  { href: "/tables", label: "Tables" },
] as const;

/**
 * Return whether a nav href is the current page.
 *
 * @param pathname - `usePathname()` value.
 * @param href - Nav target.
 * @returns True for exact `/` or prefix match on nested routes.
 */
export function navItemIsCurrent(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Render production Chat/Documents/Graph/Tables links.
 *
 * @returns List of Next.js `Link` items.
 * @remarks
 * Omitting a link does not imply HTTP 403.
 */
export function AppNav() {
  const pathname = usePathname() ?? "/";
  return (
    <ul className={styles.navList}>
      {NAV_ITEMS.map((item) => (
        <li key={item.href} className={styles.navRow}>
          <Link
            href={item.href}
            aria-current={navItemIsCurrent(pathname, item.href) ? "page" : undefined}
          >
            {item.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}
