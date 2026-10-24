// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { RATE_LIMIT_COPY } from "../lib/admin-copy";
import { SessionProvider } from "../lib/auth/session-provider";
import { AdminApp } from "./admin/admin-app";
import { AccountPanel } from "./admin/account-panel";
import { CurationPanel } from "./admin/curation-panel";
import { TeamAccessPanel } from "./admin/team-access-panel";
import { ToolsPanel } from "./admin/tools-panel";
import { UsagePanel } from "./admin/usage-panel";

const fetchMe = vi.fn();
const createInvitation = vi.fn();
const offboardUser = vi.fn();
const listWorkspaceUsers = vi.fn();
const enableTool = vi.fn();
const listTools = vi.fn();
const fetchUsageMe = vi.fn();
const fetchUsageCompany = vi.fn();
const fetchReady = vi.fn();
const loadConsoleReadiness = vi.fn();
const fetchMeta = vi.fn();
const approveEntityRule = vi.fn();
const listEntityRules = vi.fn();
const patchEntityRule = vi.fn();
const suggestEntityRule = vi.fn();
const routerReplace = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin",
  useSearchParams: () => new URLSearchParams("tab=team"),
  useRouter: () => ({
    push: vi.fn(),
    replace: routerReplace,
    prefetch: vi.fn(),
  }),
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
    loadConsoleReadiness: (...args: unknown[]) => loadConsoleReadiness(...args),
    createInvitation: (...args: unknown[]) => createInvitation(...args),
    offboardUser: (...args: unknown[]) => offboardUser(...args),
    listWorkspaceUsers: (...args: unknown[]) => listWorkspaceUsers(...args),
    enableTool: (...args: unknown[]) => enableTool(...args),
    listTools: (...args: unknown[]) => listTools(...args),
    fetchUsageMe: (...args: unknown[]) => fetchUsageMe(...args),
    fetchUsageCompany: (...args: unknown[]) => fetchUsageCompany(...args),
    listEntityRules: (...args: unknown[]) => listEntityRules(...args),
    approveEntityRule: (...args: unknown[]) => approveEntityRule(...args),
    patchEntityRule: (...args: unknown[]) => patchEntityRule(...args),
    suggestEntityRule: (...args: unknown[]) => suggestEntityRule(...args),
  };
});

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  routerReplace.mockReset();
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
  loadConsoleReadiness.mockResolvedValue({
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
  listWorkspaceUsers.mockResolvedValue({
    members: [
      {
        user_id: "u-owner",
        email: "owner@example.com",
        display_name: "Owner",
        role: "owner",
        upload_enabled: true,
        disabled_at: null,
        created_at: "2026-08-01T00:00:00Z",
      },
      {
        user_id: "u-member",
        email: "<img src=x onerror=alert(1)>@evil.test",
        display_name: null,
        role: "member",
        upload_enabled: false,
        disabled_at: null,
        created_at: "2026-08-02T00:00:00Z",
      },
    ],
    pending_invitations: [
      {
        invitation_id: "inv-pending",
        email: "pending@example.com",
        role: "viewer",
        upload_enabled: false,
        expires_at: "2099-01-01T00:00:00Z",
        created_at: "2026-08-03T00:00:00Z",
      },
    ],
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
  approveEntityRule.mockResolvedValue({
    rule_id: "rule-1",
    row_version: 2,
  });
  patchEntityRule.mockResolvedValue({
    rule_id: "rule-1",
    row_version: 5,
  });
  suggestEntityRule.mockResolvedValue({
    rule_id: "rule-s",
    row_version: 1,
    invalidated: false,
  });
  createInvitation.mockResolvedValue({
    invitation_id: "inv-1",
    email: "<img src=x onerror=alert(1)>@evil.test",
    role: "member",
    upload_enabled: false,
    expires_at: "2026-08-18T00:00:00Z",
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

describe("AdminApp", () => {
  it("shows a permission error after a real 403 for a member", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u-member",
      role: "member",
      authorization_version: 1,
      upload_enabled: true,
    });
    listEntityRules.mockRejectedValue(new Error("forbidden"));
    renderSurface(<AdminApp />);
    expect(await screen.findByText("You don’t have access.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send invitation" })).toBeNull();
    expect(screen.queryByText(/bootstrap/i)).toBeNull();
  });

  it("lets an owner switch tabs through URL state", async () => {
    renderSurface(<AdminApp />);
    expect(await screen.findByRole("tab", { name: "Team & access" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.click(screen.getByRole("tab", { name: "Tools" }));
    expect(routerReplace).toHaveBeenCalledWith("/admin?tab=tools");
    expect(screen.queryByRole("tab", { name: "Names & aliases" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Evaluation" })).toBeNull();
  });

  it("shows Evaluation only when /api/meta reports the capability", async () => {
    fetchMeta.mockResolvedValue({
      api_version: "1",
      sse_schema_version: "1",
      min_client_version: "0.1.0",
      pdf_eval_workspace: true,
    });
    renderSurface(<AdminApp />);
    expect(await screen.findByRole("tab", { name: "Evaluation" })).toBeInTheDocument();
  });
});

describe("TeamAccessPanel", () => {
  it("hides invite and offboard for a viewer", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u-viewer",
      role: "viewer",
      authorization_version: 1,
      upload_enabled: false,
    });
    renderSurface(<TeamAccessPanel />);
    await waitFor(() => expect(fetchMe).toHaveBeenCalled());
    expect(screen.queryByTestId("invite-form")).toBeNull();
    expect(screen.queryByTestId("offboard-form")).toBeNull();
    expect(screen.queryByRole("button", { name: "Send invitation" })).toBeNull();
    expect(createInvitation).toBeDefined();
    expect(offboardUser).toBeDefined();
    expect(screen.queryByText(/bootstrap/i)).toBeNull();
    expect(screen.queryByRole("table", { name: /workspace people/i })).toBeNull();
    expect(screen.queryByRole("table", { name: /pending invitations/i })).toBeNull();
  });

  it("does not render an invitation token and keeps hostile email as text", async () => {
    renderSurface(<TeamAccessPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Invite teammate" }));
    const email = await screen.findByLabelText("Email");
    fireEvent.change(email, {
      target: { value: "teammate@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByTestId("invite-mail-only")).toHaveTextContent(
      "The invitation token is delivered by mail only",
    );
    expect(screen.queryByTestId("raw-token")).toBeNull();
    expect(screen.queryByText("once-secret")).toBeNull();
    expect(screen.queryByLabelText("Email")).toBeNull();
    expect(screen.getByTestId("invite-mail-only")).toHaveTextContent("<img src=x onerror=alert(1)>@evil.test");
    expect(document.querySelector("img")).toBeNull();
  });

  it("lists workspace people and pending invitations for an owner", async () => {
    renderSurface(<TeamAccessPanel />);
    expect(await screen.findByRole("table", { name: "Workspace people" })).toBeInTheDocument();
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)>@evil.test")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByRole("table", { name: "Pending invitations" })).toBeInTheDocument();
    expect(screen.getByText("pending@example.com")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Offboard" })[0]!);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("filters people by name and recovers from an empty search", async () => {
    renderSurface(<TeamAccessPanel />);
    const search = await screen.findByLabelText("Find a person");
    fireEvent.change(search, { target: { value: "Owner" } });
    expect(screen.getByRole("table", { name: "Workspace people" })).toHaveTextContent("owner@example.com");
    expect(within(screen.getByRole("table", { name: "Workspace people" })).queryByText(/evil.test/)).toBeNull();
    fireEvent.change(search, { target: { value: "no such person" } });
    expect(screen.getByText("No matching people.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reset people filters" }));
    expect(screen.getByRole("table", { name: "Workspace people" })).toHaveTextContent("evil.test");
  });

  it("preserves an unfinished invitation and explains viewer permissions", async () => {
    createInvitation.mockClear();
    renderSurface(<TeamAccessPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Invite teammate" }));
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "draft@example.com" } });
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "viewer" } });
    expect(screen.getByLabelText("Upload access")).toBeDisabled();
    expect(screen.getByText(/Viewers can read and ask questions/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close invitation" }));
    fireEvent.click(screen.getByRole("button", { name: "Invite teammate" }));
    expect(screen.getByLabelText("Email")).toHaveValue("draft@example.com");
    expect(createInvitation).not.toHaveBeenCalled();
  });

  it("offboards the selected person only after confirmation, without requiring an ID", async () => {
    offboardUser.mockClear();
    renderSurface(<TeamAccessPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Offboard" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("<img src=x onerror=alert(1)>@evil.test");
    expect(screen.queryByLabelText("User ID")).toBeNull();
    expect(offboardUser).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Offboard user" }));
    expect(await screen.findByTestId("offboard-result")).toHaveTextContent("Access removed for");
    expect(offboardUser).toHaveBeenCalledWith(
      { accessToken: "jwt-token" },
      "u-member",
    );
    expect(screen.queryByText(/MFA|AAL2|assurance/i)).toBeNull();
  });
});

describe("ToolsPanel", () => {
  it("hides enable for a member, searches with q, and has no seed form", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u-member",
      role: "member",
      authorization_version: 1,
      upload_enabled: true,
    });
    renderSurface(<ToolsPanel />);
    expect(await screen.findByText("CSV export")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Disable" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Enable" })).toBeNull();
    expect(screen.queryByText("admin_secret_tool")).toBeNull();
    expect(screen.queryByRole("button", { name: /seed/i })).toBeNull();
    fireEvent.change(screen.getByLabelText("Search tools"), {
      target: { value: "csv export" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(listTools).toHaveBeenCalledWith({ accessToken: "jwt-token" }, "csv export");
    expect(enableTool).toBeDefined();
  });

  it("clears a tool search back to the full catalog", async () => {
    renderSurface(<ToolsPanel />);
    await screen.findByText("CSV export");
    fireEvent.change(screen.getByLabelText("Search tools"), { target: { value: "csv" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(listTools).toHaveBeenCalledWith({ accessToken: "jwt-token" }, "csv"));
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(screen.getByLabelText("Search tools")).toHaveValue("");
    await waitFor(() => expect(listTools).toHaveBeenLastCalledWith({ accessToken: "jwt-token" }, ""));
  });

  it("lets an owner disable a tool through the catalog seed", async () => {
    renderSurface(<ToolsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Disable" }));
    await waitFor(() =>
      expect(enableTool).toHaveBeenCalledWith(
        { accessToken: "jwt-token" },
        "export_csv",
        false,
      ),
    );
  });
});

describe("UsagePanel", () => {
  it("shows token meters and no budget slider or fake audit events", async () => {
    renderSurface(<UsagePanel />);
    expect(await screen.findByText("$1.25")).toBeInTheDocument();
    expect(screen.getByText("Your usage")).toBeInTheDocument();
    expect(screen.getByText(/Recorded model usage/)).toBeInTheDocument();
    expect(screen.getAllByText("Prompt tokens").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Usage records").length).toBeGreaterThan(0);
    expect(screen.getByTestId("usage-meters")).toBeInTheDocument();
    expect(await screen.findByTestId("company-usage-meters")).toBeInTheDocument();
    expect(screen.queryByTestId("budget-editor-unavailable")).toBeNull();
    expect(screen.queryByTestId("audit-unavailable")).toBeNull();
    expect(screen.queryByRole("slider")).toBeNull();
    expect(document.querySelector("input[type='range']")).toBeNull();
    expect(screen.queryByText("SECRET_PASSAGE")).toBeNull();
    expect(screen.queryByRole("table", { name: /audit/i })).toBeNull();
  });

  it("refreshes both authorized summaries and labels cost as an estimate", async () => {
    renderSurface(<UsagePanel />);
    expect(await screen.findByText("$1.25")).toBeInTheDocument();
    expect(screen.getAllByText("Recorded cost estimate")).toHaveLength(2);
    expect(screen.getByText(/not a verified provider invoice/)).toBeInTheDocument();
    const refresh = await screen.findByRole("button", { name: "Refresh usage" });
    const meCalls = fetchUsageMe.mock.calls.length;
    const companyCalls = fetchUsageCompany.mock.calls.length;
    fireEvent.click(refresh);
    await waitFor(() => expect(fetchUsageMe.mock.calls.length).toBeGreaterThan(meCalls));
    await waitFor(() => expect(fetchUsageCompany.mock.calls.length).toBeGreaterThan(companyCalls));
  });

  it("shows unavailable totals rather than fabricated zero usage on failure", async () => {
    fetchUsageMe.mockRejectedValue(new Error("invalid_usage_response"));
    fetchUsageCompany.mockRejectedValue(new Error("invalid_usage_response"));
    renderSurface(<UsagePanel />);
    await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(2));
    expect(screen.queryByText("$0.00")).toBeNull();
    expect(screen.queryByText("No model usage has been recorded yet.")).toBeNull();
  });

  it("hides company meters for a member without audit chrome", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u-member",
      role: "member",
      authorization_version: 1,
      upload_enabled: true,
    });
    fetchUsageCompany.mockRejectedValue(new Error("forbidden"));
    loadConsoleReadiness.mockResolvedValue({
      status: "degraded",
      query_ready: true,
      detail: "ok",
      rate_limit_degraded: true,
      dependencies: [],
    });
    renderSurface(<UsagePanel />);
    expect(await screen.findByTestId("usage-meters")).toBeInTheDocument();
    expect(screen.queryByTestId("company-usage-meters")).toBeNull();
    expect(screen.queryByTestId("audit-unavailable")).toBeNull();
    expect(await screen.findByText(/Rate limiter is degraded/)).toBeInTheDocument();
    expect(screen.getByText(RATE_LIMIT_COPY, { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("SECRET_PASSAGE")).toBeNull();
    expect(document.querySelector("input[type='range']")).toBeNull();
  });
});

describe("AccountPanel", () => {
  it("shows /me fields and has no settings save", async () => {
    renderSurface(<AccountPanel />);
    expect(await screen.findByText("u-owner")).toBeInTheDocument();
    expect(screen.getByText("User ID")).toBeInTheDocument();
    expect(screen.getByText("Owner")).toBeInTheDocument();
    expect(screen.getByText("Upload access")).toBeInTheDocument();
    expect(screen.queryByTestId("profile-editor-unavailable")).toBeNull();
    expect(screen.queryByTestId("company-settings-unavailable")).toBeNull();
    expect(screen.queryByRole("button", { name: /save/i })).toBeNull();
    expect(screen.queryByLabelText(/locale/i)).toBeNull();
    expect(screen.queryByText(/mfa_enrolled/i)).toBeNull();
  });
});

describe("CurationPanel", () => {
  it("hides glossary and entity-rule mutations for a viewer", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u-viewer",
      role: "viewer",
      authorization_version: 1,
      upload_enabled: false,
    });
    renderSurface(<CurationPanel />);
    expect(await screen.findByText(/Names and aliases are limited/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import glossary" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("explains word aliases and people-and-things for an owner", async () => {
    renderSurface(<CurationPanel />);
    expect(
      await screen.findByText(/Teach search your company's language/),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Word aliases" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "People & things" })).toBeInTheDocument();
    expect(screen.getByText(/Add a company term and optional nickname/)).toBeInTheDocument();
  });

  it("approves an entity rule with row_version only for an owner", async () => {
    listEntityRules.mockResolvedValue({
      rules: [
        {
          id: "rule-1",
          entity_type: "ORG",
          canonical_name: "<script>x</script>",
          aliases: [],
          do_not_merge: [],
          status: "proposed",
          source: "admin",
          row_version: 4,
        },
      ],
    });
    renderSurface(<CurationPanel />);
    fireEvent.click(await screen.findByRole("tab", { name: "People & things" }));
    fireEvent.click(await screen.findByRole("button", { name: "Rule actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Approve" }));
    expect(await screen.findByText("Rule approved.")).toBeInTheDocument();
    expect(approveEntityRule).toHaveBeenCalledWith(
      { accessToken: "jwt-token" },
      "rule-1",
      4,
    );
    expect(screen.getByText("<script>x</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });

  it("shows Reload rule after a stale PATCH", async () => {
    listEntityRules.mockResolvedValue({
      rules: [
        {
          id: "rule-1",
          entity_type: "ORG",
          canonical_name: "Acme",
          aliases: ["co"],
          do_not_merge: [],
          status: "approved",
          source: "admin",
          row_version: 4,
        },
      ],
    });
    patchEntityRule.mockRejectedValue(new Error("stale_row_version"));
    renderSurface(<CurationPanel />);
    fireEvent.click(await screen.findByRole("tab", { name: "People & things" }));
    fireEvent.click(await screen.findByRole("button", { name: "Rule actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Save rule" }));
    expect(await screen.findByRole("button", { name: "Reload rule" })).toBeInTheDocument();
  });
});
