/**
 * Console information architecture for the P08-14 shell.
 *
 * Nav visibility is convenience only. FastAPI still authorizes every call.
 */

import { isOwnerOrAdmin } from "./roles";
import type { IconName } from "../components/ui/icon";
import type { ReadinessResponse } from "./types";

/** One primary console destination. */
export type ShellNavItem = {
  /** Pathname. */
  href: string;
  /** Visible English label. */
  label: string;
  /** Lucide icon id. */
  icon: IconName;
  /** Stable `data-action-id`. */
  actionId: string;
  /** Stable `data-testid`. */
  testId: string;
};

/** Ask, Documents, Tables, Graph — in that order. */
export const PRIMARY_NAV_ITEMS: readonly ShellNavItem[] = [
  {
    href: "/",
    label: "Ask",
    icon: "chat",
    actionId: "nav.ask",
    testId: "nav-ask",
  },
  {
    href: "/documents",
    label: "Documents",
    icon: "documents",
    actionId: "nav.documents",
    testId: "nav-documents",
  },
  {
    href: "/tables",
    label: "Tables",
    icon: "tables",
    actionId: "nav.tables",
    testId: "nav-tables",
  },
  {
    href: "/graph",
    label: "Graph",
    icon: "graph",
    actionId: "nav.graph",
    testId: "nav-graph",
  },
];

/** Single Admin destination. Shown only for owner/admin convenience. */
export const ADMIN_NAV_ITEM: ShellNavItem = {
  href: "/admin",
  label: "Admin",
  icon: "lock",
  actionId: "nav.admin",
  testId: "nav-admin",
};

/** Account details destination. Not a primary-nav row. */
export const ACCOUNT_NAV_ITEM: ShellNavItem = {
  href: "/account",
  label: "Account details",
  icon: "profile",
  actionId: "nav.account",
  testId: "nav-account",
};

/** Admin query-tab ids. Evaluation appears only when `/api/meta` allows it. */
export const ADMIN_TABS = ["overview", "team", "tools", "knowledge", "usage", "evaluation"] as const;

/** Admin tab union. */
export type AdminTab = (typeof ADMIN_TABS)[number];

/**
 * Bookmark map from retired Manage/Profile URLs to the P08-14 destinations.
 */
export const LEGACY_CONSOLE_REDIRECTS: Readonly<Record<string, string>> = {
  "/team": "/admin?tab=team",
  "/tools": "/admin?tab=tools",
  "/curation": "/admin?tab=team",
  "/usage": "/admin?tab=usage",
  "/profile": "/account",
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
 * Return whether the Admin nav item may render.
 *
 * @param role - Live `GET /me` role.
 * @returns Convenience flag. Forged members still receive server 403s.
 */
export function showAdminNav(role: string | undefined): boolean {
  return isOwnerOrAdmin(role);
}

/**
 * Return Admin tabs visible for this handshake.
 *
 * Hidden Evaluation is convenience only. FastAPI still 403s members.
 *
 * @param pdfEvalWorkspace - `/api/meta` capability.
 * @returns Tabs to render.
 */
export function visibleAdminTabs(pdfEvalWorkspace: boolean): readonly AdminTab[] {
  if (pdfEvalWorkspace) {
    return ADMIN_TABS;
  }
  return ADMIN_TABS.filter((id) => id !== "evaluation");
}

/**
 * Normalize `?tab=` for `/admin`.
 *
 * @param value - Raw search param.
 * @param pdfEvalWorkspace - Handshake capability. Unknown or unauthorized
 *   Evaluation values fall back to Overview.
 * @returns Known tab. Unknown values fall back to Overview.
 */
export function parseAdminTab(
  value: string | undefined,
  pdfEvalWorkspace = false,
): AdminTab {
  if (value === "overview" || value === "team" || value === "tools" || value === "usage" || value === "knowledge") {
    return value;
  }
  if (value === "evaluation" && pdfEvalWorkspace) {
    return "evaluation";
  }
  return value === "curation" ? "team" : "overview";
}

/**
 * Return whether a pathname is a retired review/gap URL that must 404.
 *
 * @param pathname - Request path.
 * @returns True for `/review-fixtures` and `/unavailable/*`.
 */
export function isRetiredProductPath(pathname: string): boolean {
  return pathname === "/review-fixtures" || pathname.startsWith("/unavailable/");
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
  if (pathname.startsWith("/admin")) {
    return "Admin";
  }
  if (pathname.startsWith("/account")) {
    return "Account";
  }
  const match = PRIMARY_NAV_ITEMS.find((item) =>
    item.href === "/"
      ? pathname === "/"
      : pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
  return match?.label ?? "Console";
}

/** Readiness chip label. */
export type ReadinessHeadline = "Checking" | "Ready" | "Degraded" | "Unavailable";

/**
 * Map a readiness payload to the four allowed chip labels.
 *
 * @param ready - Merged console payload, undefined while loading, null when unreachable.
 * @returns Headline. `query_ready` false is Unavailable, not Degraded.
 */
export function readinessHeadline(
  ready: ReadinessResponse | null | undefined,
): ReadinessHeadline {
  if (ready === undefined) {
    return "Checking";
  }
  if (ready === null || ready.query_ready !== true) {
    return "Unavailable";
  }
  if (ready.rate_limit_degraded) {
    return "Degraded";
  }
  return "Ready";
}

/** One capability row in the readiness popover. */
export type ReadinessCapability = {
  /** Stable id. */
  id: string;
  /** User-facing label authorized by a real field. */
  label: string;
  /** Whether that field reports healthy. */
  ok: boolean;
};

/**
 * Build capability rows from real readiness fields only.
 *
 * Question answering always appears (`query_ready`). Keyword/Graph rows appear
 * only when operator `dependencies` include those probes.
 *
 * @param ready - Merged payload.
 * @returns Rows. Never invents provider copy from missing fields.
 */
export function readinessCapabilities(
  ready: ReadinessResponse,
): ReadinessCapability[] {
  const rows: ReadinessCapability[] = [
    {
      id: "qa",
      label: "Question answering",
      ok: ready.query_ready,
    },
  ];
  for (const dependency of ready.dependencies) {
    const name = dependency.name.toLowerCase();
    const ok =
      dependency.status === "ok" ||
      dependency.status === "up" ||
      dependency.status === "ready";
    if (name.includes("parade") || name.includes("bm25")) {
      rows.push({ id: `kw-${dependency.name}`, label: "Keyword search", ok });
    }
    if (name.includes("lightrag") || name.includes("graph")) {
      rows.push({ id: `graph-${dependency.name}`, label: "Graph search", ok });
    }
  }
  return rows;
}

/**
 * Blocking copy when question answering is down.
 *
 * @returns Handshake sentence. No DSNs or stack traces.
 */
export function readinessBlockingCopy(): string {
  return "Question answering is temporarily unavailable. Try again when the service is ready.";
}

/**
 * Command-palette destinations for the signed-in role.
 *
 * @param role - Live `GET /me` role.
 * @returns Supported routes only. Sign out is a separate row.
 */
export function commandDestinations(role: string | undefined): ShellNavItem[] {
  const items: ShellNavItem[] = [...PRIMARY_NAV_ITEMS];
  if (showAdminNav(role)) {
    items.push(ADMIN_NAV_ITEM);
  }
  items.push(ACCOUNT_NAV_ITEM);
  return items;
}
