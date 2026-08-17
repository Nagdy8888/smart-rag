/**
 * Client nav so `aria-current` tracks the real pathname.
 * Nav is not authorization.
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import styles from "./app-shell.module.css";

const NAV_ITEMS = [
  { href: "/", label: "Chat" },
  { href: "/documents", label: "Documents" },
  { href: "/graph", label: "Graph" },
  { href: "/tables", label: "Tables" },
  { href: "/team", label: "Team" },
  { href: "/tools", label: "Tools" },
  { href: "/curation", label: "Curation" },
  { href: "/usage", label: "Usage" },
  { href: "/profile", label: "Profile" },
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
 * Render production Chat through Profile links.
 *
 * @returns List of Next.js `Link` items, or a disclosure Menu under 801px.
 * @remarks
 * Omitting a link does not imply HTTP 403. Mobile uses a disclosure
 * summary labeled Menu. Placeholder hash links are forbidden.
 */
export function AppNav() {
  const pathname = usePathname() ?? "/";
  const [desktop, setDesktop] = useState(true);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const media = window.matchMedia("(min-width: 801px)");
    const update = (): void => {
      setDesktop(media.matches);
    };
    update();
    media.addEventListener("change", update);
    return () => {
      media.removeEventListener("change", update);
    };
  }, []);

  const list = (
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

  if (desktop) {
    return list;
  }

  return (
    <details className={styles.navMenu}>
      <summary>Menu</summary>
      {list}
    </details>
  );
}
