/**
 * Console navigation: Ask/Documents/Tables/Graph, optional Admin, command,
 * readiness, and Account. Nav is not an authorization boundary.
 */

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMe } from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { sessionQueryKeys } from "../../lib/query-keys";
import {
  ACCOUNT_NAV_ITEM,
  ADMIN_NAV_ITEM,
  PRIMARY_NAV_ITEMS,
  consolePageTitle,
  navItemIsCurrent,
  showAdminNav,
  type ShellNavItem,
} from "../../lib/shell-navigation";
import { Button } from "./button";
import { CommandMenu, useCommandMenuShortcut } from "./command-menu";
import { Icon, type IconName } from "./icon";
import { Menu } from "./menu";
import { ReadinessIndicator } from "./readiness-indicator";
import { Sheet } from "./sheet";
import { Tooltip } from "./tooltip";
import { UserText } from "./user-text";
import styles from "./app-shell.module.css";

export { navItemIsCurrent, consolePageTitle };

/**
 * Render one grouped list of console links.
 *
 * @param items - Route descriptors.
 * @param pathname - Current path.
 * @returns List of links.
 */
function NavList({
  items,
  pathname,
}: {
  items: readonly ShellNavItem[];
  pathname: string;
}) {
  return (
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
                data-action-id={item.actionId}
                data-testid={item.testId}
              >
                <Icon name={item.icon} />
                <span className={styles.navLabel}>{item.label}</span>
              </Link>
            </Tooltip>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Render Ask, Documents, Tables, Graph, and optional Admin.
 *
 * @returns Next.js `Link` lists. Placeholder hash links are forbidden.
 */
export function AppNav() {
  const pathname = usePathname() ?? "/";
  const session = useSession();
  const token = session.accessToken;
  const auth = token === null ? null : { accessToken: token };
  const meQuery = useQuery({
    queryKey: sessionQueryKeys(token).me,
    queryFn: () => fetchMe(auth!),
    enabled: auth !== null,
  });
  const adminVisible = showAdminNav(meQuery.data?.role);
  return (
    <div className={styles.navGroups}>
      <div className={styles.navGroup}>
        <NavList items={PRIMARY_NAV_ITEMS} pathname={pathname} />
      </div>
      {adminVisible ? (
        <div className={styles.navAdmin}>
          <NavList items={[ADMIN_NAV_ITEM]} pathname={pathname} />
        </div>
      ) : null}
    </div>
  );
}

/**
 * Render Account menu: live /me fields, upload flag, details link, Sign out.
 *
 * @returns Account control. Never renders mfa_enrolled.
 */
export function AccountMenu() {
  const session = useSession();
  const router = useRouter();
  const token = session.accessToken;
  const auth = token === null ? null : { accessToken: token };
  const meQuery = useQuery({
    queryKey: sessionQueryKeys(token).me,
    queryFn: () => fetchMe(auth!),
    enabled: auth !== null,
  });
  if (!session.ready || token === null) {
    return null;
  }
  const me = meQuery.data;
  const initials = (session.email ?? "U").slice(0, 2).toUpperCase();
  const uploadLabel =
    me?.upload_enabled === true ? "Uploads enabled" : "Uploads disabled";
  return (
    <Menu
      label="Account"
      trigger={
        <>
          <span className={styles.avatarMark} aria-hidden="true">
            {initials}
          </span>
          <span className={styles.srOnly}>Account</span>
        </>
      }
      items={[
        {
          id: "identity",
          label: (
            <span>
              <UserText value={session.email ?? ""} />
              <span>
                {" "}
                | <UserText value={me?.role ?? ""} /> | {uploadLabel}
              </span>
            </span>
          ),
          disabled: true,
          onSelect: () => undefined,
        },
        {
          id: "account",
          label: ACCOUNT_NAV_ITEM.label,
          actionId: ACCOUNT_NAV_ITEM.actionId,
          onSelect: () => {
            router.push(ACCOUNT_NAV_ITEM.href);
          },
        },
        {
          id: "sign-out",
          label: "Sign out",
          danger: true,
          actionId: "account.sign_out",
          onSelect: () => {
            void session.signOut();
          },
        },
      ]}
    />
  );
}

export type ConsoleTopbarProps = {
  /** Desktop console rail visibility. */
  navExpanded?: boolean;
  /** Restore the desktop rail. Shown in the topbar while the rail is collapsed. */
  onExpandNav?: () => void;
};

/**
 * Render the 56px console top bar: menu, title, readiness, command, account.
 *
 * @param props - Optional desktop nav expand control.
 * @returns Header contents and overlays.
 */
export function ConsoleTopbar({
  navExpanded = true,
  onExpandNav,
}: ConsoleTopbarProps) {
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandEpoch, setCommandEpoch] = useState(0);
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const openCommand = useCallback(() => {
    setCommandEpoch((value) => value + 1);
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

  const pathname = usePathname() ?? "/";

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
          data-action-id="shell.menu"
          data-testid="shell-menu"
          onClick={() => {
            setMobileOpen(true);
          }}
        >
          <Icon name="menu" />
          <span className={styles.srOnly}>Menu</span>
        </Button>
        {onExpandNav && !navExpanded ? (
          <Button
            type="button"
            variant="secondary"
            className={styles.navExpand}
            aria-expanded={false}
            data-action-id="shell.nav_toggle"
            onClick={onExpandNav}
          >
            <Icon name="panelExpand" />
            Expand navigation
          </Button>
        ) : null}
        <h1 className={styles.topbarTitle}>{consolePageTitle(pathname)}</h1>
      </div>
      <div className={styles.topbarEnd}>
        <ReadinessIndicator />
        <Tooltip text="Go to page">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={styles.commandButton}
            aria-label="Open command menu"
            data-action-id="shell.command"
            data-testid="shell-command"
            onClick={openCommand}
          >
            <Icon name="command" />
            <span className={styles.srOnly}>Command menu</span>
          </Button>
        </Tooltip>
        <span data-action-id="shell.account" data-testid="shell-account">
          <AccountMenu />
        </span>
      </div>
      <CommandMenu key={commandEpoch} open={commandOpen} onClose={() => setCommandOpen(false)} />
      {mobileOpen ? (
        <Sheet
          title="Menu"
          onClose={() => {
            setMobileOpen(false);
          }}
          returnFocusRef={menuButtonRef}
          side="left"
        >
          <AppNav />
        </Sheet>
      ) : null}
    </>
  );
}

export type { IconName };
