// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import "@testing-library/jest-dom/vitest";
import { CLIENT_NAV_IS_NOT_AUTHORIZATION } from "../../lib/client-authorization";
import { AppShell } from "./app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
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
  it("exposes a skip link, 280px token nav, and main landmark", () => {
    render(
      <AppShell>
        <p>Console body</p>
      </AppShell>,
    );
    const skip = screen.getByRole("link", { name: "Skip to main content" });
    expect(skip).toHaveAttribute("href", "#main");
    expect(screen.getByRole("navigation", { name: "Console" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/");
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
