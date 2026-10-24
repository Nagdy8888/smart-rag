/**
 * Console navigation: Ask/Documents/Tables/Graph, optional Admin, command,
 * readiness, and Account. Nav is not an authorization boundary.
 */

"use client";

import accountStyles from "./account-menu.module.css";
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
import navStyles from "./app-nav.module.css";
import layoutStyles from "./app-shell.module.css";
import topbarStyles from "./app-topbar.module.css";

const styles = { ...layoutStyles, ...navStyles, ...topbarStyles };

export { navItemIsCurrent };

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
            <Tooltip text={item.label} placement="end">
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
    return (
      <span
        className={styles.avatarMark}
        aria-hidden="true"
        data-testid="account-avatar-placeholder"
      >
        ··
      </span>
    );
  }
  const me = meQuery.data;
  const initials = (session.email ?? "U").slice(0, 2).toUpperCase();
  const uploadLabel =
    me ? (me.upload_enabled ? "Uploads enabled" : "Uploads disabled")
      : meQuery.isPending ? "Checking access" : "Access unavailable";
  return (
    <Menu
      label="Account"
      triggerActionId="shell.account"
      panelClassName={accountStyles.panel}
      header={
        <div className={accountStyles.profile}>
          <span className={accountStyles.profileAvatar} aria-hidden="true">{initials}</span>
          <div className={accountStyles.identity}>
            <p className={accountStyles.caption}>Signed in as</p>
            <p className={accountStyles.email}><UserText value={session.email ?? ""} /></p>
            <div className={accountStyles.badges}>
              <span className={accountStyles.role}><UserText value={me?.role ?? (meQuery.isPending ? "Checking role" : "Role unavailable")} /></span>
              <span className={accountStyles.access} data-enabled={me?.upload_enabled === true ? "true" : "false"}>{uploadLabel}</span>
            </div>
          </div>
        </div>
      }
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
          id: "account",
          label: <span className={accountStyles.action}><Icon name="profile" /><span><strong>{ACCOUNT_NAV_ITEM.label}</strong><span className={accountStyles.actionHint}>View your account information</span></span></span>,
          actionId: ACCOUNT_NAV_ITEM.actionId,
          onSelect: () => {
            router.push(ACCOUNT_NAV_ITEM.href);
          },
        },
        {
          id: "sign-out",
          label: <span className={accountStyles.action}><Icon name="logout" /><strong>Sign out</strong></span>,
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
  /** Unused. Collapse lives on the nav rail. Kept for existing imports. */
  navExpanded?: boolean;
  /** Unused. Collapse lives on the nav rail. */
  onExpandNav?: () => void;
};

/**
 * Render the 56px console top bar: menu, title, readiness, command, account.
 *
 * @param _props - Optional unused expand props (rail owns collapse).
 * @returns Header contents and overlays.
 */
export function ConsoleTopbar() {
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
      </div>
      <div className={styles.topbarEnd}>
        <ReadinessIndicator />
        <Tooltip text="Quick navigation (Ctrl+K or Command+K)">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            id="shell-command"
            className={styles.commandButton}
            aria-label="Open command menu"
            data-action-id="shell.command"
            data-testid="shell-command"
            onClick={openCommand}
          >
            <Icon name="search" />
            <span className={styles.commandLabel}>Go to page</span>
            <kbd className={styles.commandShortcut}>Ctrl K</kbd>
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
