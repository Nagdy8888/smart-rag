/**
 * Console navigation: grouped Work/Manage routes, command menu, readiness.
 * Nav is not an authorization boundary.
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { loadConsoleReadiness } from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { sessionQueryKeys } from "../../lib/query-keys";
import { Button } from "./button";
import { CommandMenu, useCommandMenuShortcut } from "./command-menu";
import { Icon, type IconName } from "./icon";
import { Menu } from "./menu";
import { Sheet } from "./sheet";
import { Tooltip } from "./tooltip";
import { UserText } from "./user-text";
import styles from "./app-shell.module.css";

type NavItem = { href: string; label: string; icon: IconName };

const WORK_ITEMS: readonly NavItem[] = [
  { href: "/", label: "Ask", icon: "chat" },
  { href: "/documents", label: "Documents", icon: "documents" },
  { href: "/graph", label: "Graph", icon: "graph" },
  { href: "/tables", label: "Tables", icon: "tables" },
];

const MANAGE_ITEMS: readonly NavItem[] = [
  { href: "/team", label: "Team", icon: "team" },
  { href: "/tools", label: "Tools", icon: "tools" },
  { href: "/curation", label: "Curation", icon: "curation" },
  { href: "/usage", label: "Usage", icon: "usage" },
];

const PAGE_TITLES: Record<string, string> = {
  "/": "Ask",
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
 * @returns Title. Nested document routes use Document.
 */
export function consolePageTitle(pathname: string): string {
  if (pathname.startsWith("/documents/")) {
    return "Document";
  }
  return PAGE_TITLES[pathname] ?? "Console";
}

/**
 * Render one grouped list of console links.
 *
 * @param items - Route descriptors.
 * @param pathname - Current path.
 * @returns List of links.
 */
function NavGroup({
  heading,
  items,
  pathname,
}: {
  heading: string;
  items: readonly NavItem[];
  pathname: string;
}) {
  return (
    <div className={styles.navGroup}>
      <p className={styles.navGroupLabel}>{heading}</p>
      <ul className={styles.navList}>
        {items.map((item) => {
          const current = navItemIsCurrent(pathname, item.href);
          return (
            <li key={item.href} className={styles.navRow}>
              <Tooltip text={item.label}>
                <Link
                  href={item.href}
                  aria-current={current ? "page" : undefined}
                  aria-label={item.label}
                >
                  <Icon name={item.icon} />
                  <span className={styles.navLabel}>{item.label}</span>
                </Link>
              </Tooltip>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/**
 * Render Work and Manage console links.
 *
 * @returns Grouped Next.js `Link` lists. Placeholder hash links are forbidden.
 */
export function AppNav() {
  const pathname = usePathname() ?? "/";
  return (
    <div className={styles.navGroups}>
      <NavGroup heading="Work" items={WORK_ITEMS} pathname={pathname} />
      <NavGroup heading="Manage" items={MANAGE_ITEMS} pathname={pathname} />
    </div>
  );
}

/**
 * Render Profile plus signed-in identity and Sign out.
 *
 * @returns Account footer. Profile remains visible without a session.
 * @remarks
 * Sign-out clears Auth cookies. FastAPI still authorizes each request.
 */
export function ShellUser() {
  const session = useSession();
  return (
    <div className={styles.userBlock}>
      {session.ready && session.accessToken !== null ? (
        <>
          <p className={styles.userEmail}>
            <UserText value={session.email ?? "Signed in"} />
          </p>
          <p className={styles.userMeta}>Company console</p>
        </>
      ) : (
        <p className={styles.userMeta}>Company console</p>
      )}
      <Link href="/profile" className={styles.profileLink}>
        <Icon name="profile" />
        <span className={styles.navLabel}>Profile</span>
      </Link>
      {session.ready && session.accessToken !== null ? (
        <Button type="button" variant="ghost" onClick={() => void session.signOut()}>
          Sign out
        </Button>
      ) : null}
    </div>
  );
}

/**
 * Render the console page title as the single visible H1.
 *
 * @returns Heading derived from the pathname.
 */
export function TopbarTitle() {
  const pathname = usePathname() ?? "/";
  return <h1 className={styles.topbarTitle}>{consolePageTitle(pathname)}</h1>;
}

/**
 * Render readiness from `loadConsoleReadiness` only.
 *
 * @returns Status text or null while unknown.
 */
function ReadinessStatus() {
  const session = useSession();
  const token = session.accessToken;
  const query = useQuery({
    queryKey: sessionQueryKeys(token).consoleReady,
    queryFn: () => loadConsoleReadiness(token === null ? null : { accessToken: token }),
    enabled: session.ready,
  });
  const ready = query.data;
  if (ready == null) {
    return null;
  }
  let label = "Not ready";
  if (ready.rate_limit_degraded) {
    label = "Degraded";
  } else if (ready.query_ready) {
    label = "Ready";
  }
  return (
    <p className={styles.readiness} data-testid="console-readiness">
      {label}
    </p>
  );
}

/**
 * Render the 56px console top bar: brand, title, readiness, command, account.
 *
 * @returns Header contents and overlays.
 */
export function ConsoleTopbar() {
  const session = useSession();
  const [commandOpen, setCommandOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const openCommand = useCallback(() => {
    setCommandOpen(true);
  }, []);
  useCommandMenuShortcut(openCommand);

  useEffect(() => {
    if (!mobileOpen) {
      return;
    }
    const media = window.matchMedia("(min-width: 1024px)");
    const closeIfDesktop = (): void => {
      if (media.matches) {
        setMobileOpen(false);
      }
    };
    media.addEventListener("change", closeIfDesktop);
    return () => {
      media.removeEventListener("change", closeIfDesktop);
    };
  }, [mobileOpen]);

  return (
    <>
      <div className={styles.topbarStart}>
        <Button
          ref={menuButtonRef}
          type="button"
          variant="ghost"
          size="icon"
          className={styles.menuButton}
          aria-label="Open navigation"
          onClick={() => {
            setMobileOpen(true);
          }}
        >
          <Icon name="menu" />
          <span className={styles.srOnly}>Menu</span>
        </Button>
        <div className={styles.topbarBrand}>
          <span className={styles.brandMark} aria-hidden="true">
            <Icon name="spark" />
          </span>
          <span className={styles.brandName}>Smart RAG</span>
        </div>
        <TopbarTitle />
      </div>
      <div className={styles.topbarEnd}>
        <ReadinessStatus />
        <Tooltip text="Go to page">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Open command menu"
            onClick={openCommand}
          >
            <Icon name="command" />
            <span className={styles.srOnly}>Command menu</span>
          </Button>
        </Tooltip>
        {session.ready && session.accessToken !== null ? (
          <Menu
            label="Account"
            trigger={
              <>
                <Icon name="profile" />
                <span className={styles.srOnly}>Account</span>
              </>
            }
            items={[
              {
                id: "profile",
                label: "Profile",
                onSelect: () => {
                  window.location.assign("/profile");
                },
              },
              {
                id: "sign-out",
                label: "Sign out",
                onSelect: () => {
                  void session.signOut();
                },
              },
            ]}
          />
        ) : null}
      </div>
      <CommandMenu open={commandOpen} onClose={() => setCommandOpen(false)} />
      {mobileOpen ? (
        <Sheet
          title="Menu"
          side="left"
          onClose={() => {
            setMobileOpen(false);
          }}
          returnFocusRef={menuButtonRef}
        >
          <AppNav />
          <ShellUser />
        </Sheet>
      ) : null}
    </>
  );
}
