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
    expect(screen.getByRole("link", { name: "Ask" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute(
      "href",
      "/documents",
    );
    expect(screen.getByRole("link", { name: "Graph" })).toHaveAttribute(
      "href",
      "/graph",
    );
    expect(screen.getByRole("link", { name: "Tables" })).toHaveAttribute(
      "href",
      "/tables",
    );
    expect(screen.getByRole("link", { name: "Team" })).toHaveAttribute(
      "href",
      "/team",
    );
    expect(screen.getByRole("link", { name: "Tools" })).toHaveAttribute(
      "href",
      "/tools",
    );
    expect(screen.getByRole("link", { name: "Curation" })).toHaveAttribute(
      "href",
      "/curation",
    );
    expect(screen.getByRole("link", { name: "Usage" })).toHaveAttribute(
      "href",
      "/usage",
    );
    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute(
      "href",
      "/profile",
    );
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
    expect(screen.getByTestId("app-shell-nav")).toBeInTheDocument();
    expect(CLIENT_NAV_IS_NOT_AUTHORIZATION).toBe(true);
    expect(screen.queryByRole("link", { name: /Stitch/i })).not.toBeInTheDocument();
  });
});
