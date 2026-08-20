/**
 * Client nav so `aria-current` tracks the real pathname.
 * Nav is not authorization.
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useSession } from "../../lib/auth/session-provider";
import { Button } from "./button";
import { Icon, type IconName } from "./icon";
import { UserText } from "./user-text";
import styles from "./app-shell.module.css";

const NAV_ITEMS: ReadonlyArray<{ href: string; label: string; icon: IconName }> = [
  { href: "/", label: "Chat", icon: "chat" },
  { href: "/documents", label: "Documents", icon: "documents" },
  { href: "/graph", label: "Graph", icon: "graph" },
  { href: "/tables", label: "Tables", icon: "tables" },
  { href: "/team", label: "Team", icon: "team" },
  { href: "/tools", label: "Tools", icon: "tools" },
  { href: "/curation", label: "Curation", icon: "curation" },
  { href: "/usage", label: "Usage", icon: "usage" },
  { href: "/profile", label: "Profile", icon: "profile" },
];

const PAGE_TITLES: Record<string, string> = {
  "/": "Chat",
  "/documents": "Documents",
  "/graph": "Graph explorer",
  "/tables": "Tables",
  "/team": "Team",
  "/tools": "Tools",
  "/curation": "Curation",
  "/usage": "Usage",
  "/profile": "Profile",
  "/invitations/accept": "Accept invitation",
};

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
 * Return the English top-bar title for a console pathname.
 *
 * @param pathname - `usePathname()` value.
 * @returns Title. Nested document routes use Documents.
 */
export function consolePageTitle(pathname: string): string {
  if (pathname.startsWith("/documents/")) {
    return "Document";
  }
  return PAGE_TITLES[pathname] ?? "Console";
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
            <Icon name={item.icon} />
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
      <summary>
        <Icon name="menu" />
        Menu
      </summary>
      {list}
    </details>
  );
}

/**
 * Render the signed-in identity in the sidebar footer.
 *
 * @returns Email, workspace label, and Sign out. Null before session restore.
 * @remarks
 * Sign-out clears Auth cookies. FastAPI still authorizes each request.
 */
export function ShellUser() {
  const session = useSession();
  if (!session.ready || session.accessToken === null) {
    return null;
  }
  return (
    <div className={styles.userBlock}>
      <p className={styles.userEmail}>
        <UserText value={session.email ?? "Signed in"} />
      </p>
      <p className={styles.userMeta}>Workspace</p>
      <Button type="button" variant="ghost" onClick={() => void session.signOut()}>
        Sign out
      </Button>
    </div>
  );
}

/**
 * Render the console top-bar title for the active route.
 *
 * @returns Heading derived from the pathname.
 */
export function TopbarTitle() {
  const pathname = usePathname() ?? "/";
  return <h2 className={styles.topbarTitle}>{consolePageTitle(pathname)}</h2>;
}
