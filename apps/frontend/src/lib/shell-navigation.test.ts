import { describe, expect, it } from "vitest";
import type { ReadinessResponse } from "./types";
import {
  ADMIN_NAV_ITEM,
  LEGACY_CONSOLE_REDIRECTS,
  PRIMARY_NAV_ITEMS,
  commandDestinations,
  consolePageTitle,
  isRetiredProductPath,
  parseAdminTab,
  readinessBlockingCopy,
  readinessCapabilities,
  readinessHeadline,
  showAdminNav,
  visibleAdminTabs,
} from "./shell-navigation";

const readyOk: ReadinessResponse = {
  status: "ok",
  query_ready: true,
  detail: "ok",
  rate_limit_degraded: false,
  dependencies: [],
};

describe("shell navigation", () => {
  it("orders Ask, Documents, Tables, Graph and gates Admin", () => {
    expect(PRIMARY_NAV_ITEMS.map((item) => item.label)).toEqual([
      "Ask",
      "Documents",
      "Tables",
      "Graph",
    ]);
    expect(showAdminNav("member")).toBe(false);
    expect(showAdminNav("viewer")).toBe(false);
    expect(showAdminNav("owner")).toBe(true);
    expect(showAdminNav("admin")).toBe(true);
    expect(ADMIN_NAV_ITEM.href).toBe("/admin");
  });

  it("maps retired bookmarks and gap routes", () => {
    expect(LEGACY_CONSOLE_REDIRECTS["/team"]).toBe("/admin?tab=team");
    expect(LEGACY_CONSOLE_REDIRECTS["/tools"]).toBe("/admin?tab=tools");
    expect(LEGACY_CONSOLE_REDIRECTS["/curation"]).toBe("/admin?tab=team");
    expect(LEGACY_CONSOLE_REDIRECTS["/usage"]).toBe("/admin?tab=usage");
    expect(LEGACY_CONSOLE_REDIRECTS["/profile"]).toBe("/account");
    expect(isRetiredProductPath("/review-fixtures")).toBe(true);
    expect(isRetiredProductPath("/unavailable/GAP-07-07")).toBe(true);
    expect(isRetiredProductPath("/login")).toBe(false);
    expect(parseAdminTab("usage")).toBe("usage");
    expect(parseAdminTab("curation")).toBe("team");
    expect(parseAdminTab("nope")).toBe("overview");
    expect(parseAdminTab("evaluation")).toBe("overview");
    expect(parseAdminTab("evaluation", true)).toBe("evaluation");
    expect(visibleAdminTabs(false)).toEqual(["overview", "team", "tools", "knowledge", "usage"]);
    expect(parseAdminTab("knowledge")).toBe("knowledge");
    expect(visibleAdminTabs(true)).toContain("evaluation");
  });

  it("titles pages and builds command destinations without MFA", () => {
    expect(consolePageTitle("/")).toBe("Ask");
    expect(consolePageTitle("/documents/abc")).toBe("Document");
    expect(consolePageTitle("/admin")).toBe("Admin");
    const member = commandDestinations("member").map((item) => item.href);
    expect(member).toEqual(["/", "/documents", "/tables", "/graph", "/account"]);
    const owner = commandDestinations("owner").map((item) => item.href);
    expect(owner).toContain("/admin");
    expect(JSON.stringify(commandDestinations("owner"))).not.toMatch(/mfa/i);
  });

  it("labels readiness from query_ready and named operator probes only", () => {
    expect(readinessHeadline(undefined)).toBe("Checking");
    expect(readinessHeadline(null)).toBe("Unavailable");
    expect(readinessHeadline({ ...readyOk, query_ready: false })).toBe(
      "Unavailable",
    );
    expect(readinessHeadline({ ...readyOk, rate_limit_degraded: true })).toBe(
      "Degraded",
    );
    expect(readinessHeadline(readyOk)).toBe("Ready");
    expect(readinessCapabilities(readyOk).map((row) => row.label)).toEqual([
      "Question answering",
    ]);
    const withDeps = readinessCapabilities({
      ...readyOk,
      dependencies: [
        { name: "paradedb", status: "ok" },
        { name: "lightrag", status: "down" },
      ],
    });
    expect(withDeps.map((row) => row.label)).toEqual([
      "Question answering",
      "Keyword search",
      "Graph search",
    ]);
    expect(withDeps[2]?.ok).toBe(false);
    expect(readinessBlockingCopy()).toContain("Question answering is temporarily unavailable");
  });
});
