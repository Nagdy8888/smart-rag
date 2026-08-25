// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CLIENT_NAV_IS_NOT_AUTHORIZATION } from "../../lib/client-authorization";
import { SessionProvider } from "../../lib/auth/session-provider";
import { AppShell } from "./app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("../../lib/auth/browser", () => ({
  createBrowserSupabase: () => ({
    auth: {
      getSession: vi.fn(async () => ({ data: { session: null } })),
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
      signOut: vi.fn(),
    },
  }),
}));

vi.mock("../../lib/env", () => ({
  publicSupabaseConfig: () => ({
    url: "http://127.0.0.1:54321",
    anonKey: "anon",
  }),
  apiBaseUrl: () => "http://127.0.0.1:8000",
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children: ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  cleanup();
});

describe("AppShell", () => {
  it("exposes a skip link, 232px token nav, and main landmark", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <AppShell>
            <p>Console body</p>
          </AppShell>
        </SessionProvider>
      </QueryClientProvider>,
    );
    const skip = screen.getByRole("link", { name: "Skip to main content" });
    expect(skip).toHaveAttribute("href", "#main");
    expect(screen.getByRole("navigation", { name: "Console" })).toBeInTheDocument();
    const ask = screen.getByRole("link", { name: "Ask" });
    const documents = screen.getByRole("link", { name: "Documents" });
    const tables = screen.getByRole("link", { name: "Tables" });
    const graph = screen.getByRole("link", { name: "Graph" });
    expect(ask).toHaveAttribute("href", "/");
    expect(documents).toHaveAttribute("href", "/documents");
    expect(tables).toHaveAttribute("href", "/tables");
    expect(graph).toHaveAttribute("href", "/graph");
    const hrefs = [ask, documents, tables, graph].map((node) => node.getAttribute("href"));
    expect(hrefs).toEqual(["/", "/documents", "/tables", "/graph"]);
    expect(screen.queryByRole("link", { name: "Team" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Tools" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Curation" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Usage" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Profile" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
    expect(screen.queryByText(/mfa_enrolled/i)).not.toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
    expect(screen.getByTestId("app-shell-nav")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Collapse navigation" }),
    ).toHaveAttribute("data-action-id", "shell.nav_toggle");
    expect(CLIENT_NAV_IS_NOT_AUTHORIZATION).toBe(true);
    expect(screen.queryByRole("link", { name: /Stitch/i })).not.toBeInTheDocument();
  });
});
