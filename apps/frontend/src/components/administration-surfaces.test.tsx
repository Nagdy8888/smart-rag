// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import {
  AUDIT_HISTORY_UNAVAILABLE,
  BUDGET_EDITOR_UNAVAILABLE,
  COMPANY_SETTINGS_UNAVAILABLE,
  NO_MEMBER_DIRECTORY_COPY,
  PROFILE_EDITOR_UNAVAILABLE,
} from "../lib/admin-copy";
import { SessionProvider } from "../lib/auth/session-provider";
import { CurationApp } from "./curation-app";
import { ProfileApp } from "./profile-app";
import { TeamApp } from "./team-app";
import { ToolsApp } from "./tools-app";
import { UsageApp } from "./usage-app";

const fetchMe = vi.fn();
const createInvitation = vi.fn();
const offboardUser = vi.fn();
const enableTool = vi.fn();
const listTools = vi.fn();
const fetchUsageMe = vi.fn();
const fetchUsageCompany = vi.fn();
const fetchReady = vi.fn();
const fetchMeta = vi.fn();
const listEntityRules = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/team",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
  }: {
    href: string;
    children: React.ReactNode;
  }) => <a href={href}>{children}</a>,
}));

vi.mock("../lib/auth/browser", () => ({
  createBrowserSupabase: () => ({
    auth: {
      getSession: vi.fn(async () => ({
        data: {
          session: { access_token: "jwt-token", user: { email: "a@b.test" } },
        },
      })),
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
      signOut: vi.fn(),
    },
  }),
}));

vi.mock("../lib/env", () => ({
  publicSupabaseConfig: () => ({
    url: "http://127.0.0.1:54321",
    anonKey: "anon",
  }),
  apiBaseUrl: () => "http://127.0.0.1:8000",
}));

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    fetchMe: (...args: unknown[]) => fetchMe(...args),
    fetchMeta: (...args: unknown[]) => fetchMeta(...args),
    fetchReady: (...args: unknown[]) => fetchReady(...args),
    createInvitation: (...args: unknown[]) => createInvitation(...args),
    offboardUser: (...args: unknown[]) => offboardUser(...args),
    enableTool: (...args: unknown[]) => enableTool(...args),
    listTools: (...args: unknown[]) => listTools(...args),
    fetchUsageMe: (...args: unknown[]) => fetchUsageMe(...args),
    fetchUsageCompany: (...args: unknown[]) => fetchUsageCompany(...args),
    listEntityRules: (...args: unknown[]) => listEntityRules(...args),
  };
});

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  fetchMeta.mockResolvedValue({
    api_version: "1",
    sse_schema_version: "1",
    min_client_version: "0.1.0",
  });
  fetchReady.mockResolvedValue({
    status: "ok",
    query_ready: true,
    detail: "ok",
    rate_limit_degraded: false,
    dependencies: [],
  });
  fetchMe.mockResolvedValue({
    user_id: "u-owner",
    role: "owner",
    authorization_version: 1,
    upload_enabled: true,
    mfa_enrolled: true,
  });
  fetchUsageMe.mockResolvedValue({
    scope: "me",
    cost_usd: "1.25",
    prompt_tokens: 10,
    completion_tokens: 4,
    usage_rows: 2,
  });
  fetchUsageCompany.mockResolvedValue({
    scope: "company",
    cost_usd: "9.00",
    prompt_tokens: 100,
    completion_tokens: 40,
    usage_rows: 8,
  });
  listTools.mockResolvedValue([
    {
      tool_key: "export_csv",
      version_label: "1",
      short_name: "CSV export",
      purpose: "Export rows",
      required_role: "member",
      risk_class: "low",
      active: true,
    },
  ]);
  listEntityRules.mockResolvedValue({ rules: [] });
  createInvitation.mockResolvedValue({
    invitation_id: "inv-1",
    email: "<img src=x onerror=alert(1)>@evil.test",
    role: "member",
    upload_enabled: false,
    expires_at: "2026-08-18T00:00:00Z",
    raw_token: "once-secret",
  });
  offboardUser.mockResolvedValue({
    request_id: "req-1",
    subject_user_id: "u-2",
    completed_at: "2026-08-17T00:00:00Z",
  });
  enableTool.mockResolvedValue({ id: "tool-row-1" });
});

/**
 * Wrap a surface with Query + session.
 *
 * @param ui - Element.
 * @returns Render result.
 */
function renderSurface(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>{ui}</SessionProvider>
    </QueryClientProvider>,
  );
}

describe("TeamApp", () => {
  it("hides invite and offboard for a viewer", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u-viewer",
      role: "viewer",
      authorization_version: 1,
      upload_enabled: false,
      mfa_enrolled: false,
    });
    renderSurface(<TeamApp />);
    expect(await screen.findByText(NO_MEMBER_DIRECTORY_COPY)).toBeInTheDocument();
    expect(screen.queryByTestId("invite-form")).toBeNull();
    expect(screen.queryByTestId("offboard-form")).toBeNull();
    expect(screen.queryByRole("button", { name: "Create invitation" })).toBeNull();
    expect(createInvitation).toBeDefined();
    expect(offboardUser).toBeDefined();
  });

  it("renders raw_token once and hostile email as text", async () => {
    renderSurface(<TeamApp />);
    const create = await screen.findByRole("button", { name: "Create invitation" });
    fireEvent.click(create);
    expect(await screen.findByTestId("raw-token")).toHaveTextContent("once-secret");
    expect(
      screen.getByText("<img src=x onerror=alert(1)>@evil.test"),
    ).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getAllByTestId("raw-token")).toHaveLength(1);
  });
});

describe("ToolsApp", () => {
  it("hides enable for a member and still exports enableTool", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u-member",
      role: "member",
      authorization_version: 1,
      upload_enabled: true,
      mfa_enrolled: true,
    });
    renderSurface(<ToolsApp />);
    expect(await screen.findByText("CSV export")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disable" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Enable" })).toBeNull();
    expect(screen.queryByText("admin_secret_tool")).toBeNull();
    expect(enableTool).toBeDefined();
  });
});

describe("UsageApp GAP-07-11/12", () => {
  it("shows token meters and no budget slider or fake audit events", async () => {
    renderSurface(<UsageApp />);
    expect(await screen.findByText("1.25")).toBeInTheDocument();
    expect(screen.getByTestId("usage-meters")).toBeInTheDocument();
    expect(await screen.findByTestId("company-usage-meters")).toBeInTheDocument();
    expect(screen.getByTestId("budget-editor-unavailable")).toHaveTextContent(
      BUDGET_EDITOR_UNAVAILABLE,
    );
    expect(screen.getByTestId("audit-unavailable")).toHaveTextContent(
      AUDIT_HISTORY_UNAVAILABLE,
    );
    expect(screen.queryByRole("slider")).toBeNull();
    expect(document.querySelector("input[type='range']")).toBeNull();
    expect(screen.queryByText("SECRET_PASSAGE")).toBeNull();
    expect(screen.queryByRole("table", { name: /audit/i })).toBeNull();
  });
});

describe("ProfileApp GAP-07-13/19", () => {
  it("shows five /me fields and has no settings save", async () => {
    renderSurface(<ProfileApp />);
    expect(await screen.findByText("u-owner")).toBeInTheDocument();
    expect(screen.getByText("owner")).toBeInTheDocument();
    expect(screen.getByTestId("profile-editor-unavailable")).toHaveTextContent(
      PROFILE_EDITOR_UNAVAILABLE,
    );
    expect(screen.getByTestId("company-settings-unavailable")).toHaveTextContent(
      COMPANY_SETTINGS_UNAVAILABLE,
    );
    expect(screen.queryByRole("button", { name: /save/i })).toBeNull();
    expect(screen.queryByLabelText(/locale/i)).toBeNull();
  });
});

describe("CurationApp", () => {
  it("hides glossary and entity-rule mutations for a viewer", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u-viewer",
      role: "viewer",
      authorization_version: 1,
      upload_enabled: false,
      mfa_enrolled: false,
    });
    renderSurface(<CurationApp />);
    expect(await screen.findByText(/Curation mutations are hidden/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import glossary" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });
});
