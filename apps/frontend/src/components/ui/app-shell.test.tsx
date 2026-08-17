// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { CLIENT_NAV_IS_NOT_AUTHORIZATION } from "../../lib/client-authorization";
import { AppShell } from "./app-shell";

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
    expect(screen.getByRole("link", { name: "Console" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
    expect(screen.getByTestId("app-shell-nav")).toBeInTheDocument();
    expect(CLIENT_NAV_IS_NOT_AUTHORIZATION).toBe(true);
    expect(screen.queryByRole("link", { name: /Stitch/i })).not.toBeInTheDocument();
  });
});
