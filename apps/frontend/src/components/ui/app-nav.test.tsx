// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppNav } from "./app-nav";

const fetchMe = vi.fn();

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

vi.mock("../../lib/api", () => ({
  fetchMe: (...args: unknown[]) => fetchMe(...args),
}));

vi.mock("../../lib/auth/session-provider", () => ({
  useSession: () => ({
    accessToken: "token",
    email: "owner@example.com",
    ready: true,
    supabase: null,
    signOut: vi.fn(),
  }),
}));

afterEach(() => {
  cleanup();
  fetchMe.mockReset();
});

function renderNav(): void {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <AppNav />
    </QueryClientProvider>,
  );
}

describe("AppNav role convenience", () => {
  it("shows Admin for owner and never treats that as authorization", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u1",
      role: "owner",
      authorization_version: 1,
      upload_enabled: true,
    });
    renderNav();
    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute(
        "href",
        "/admin",
      );
    });
    expect(screen.queryByRole("link", { name: "Team" })).not.toBeInTheDocument();
    expect(screen.queryByText(/mfa_enrolled/i)).not.toBeInTheDocument();
  });

  it("hides Admin for members while primary Ask-Documents-Tables-Graph remain", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u2",
      role: "member",
      authorization_version: 1,
      upload_enabled: false,
    });
    renderNav();
    await waitFor(() => {
      expect(fetchMe).toHaveBeenCalled();
    });
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ask" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Documents" })).toHaveAttribute(
      "href",
      "/documents",
    );
    expect(screen.getByRole("link", { name: "Tables" })).toHaveAttribute(
      "href",
      "/tables",
    );
    expect(screen.getByRole("link", { name: "Graph" })).toHaveAttribute(
      "href",
      "/graph",
    );
  });
});
