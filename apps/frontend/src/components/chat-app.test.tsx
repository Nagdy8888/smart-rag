// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { ChatApp } from "./chat-app";
import { SessionProvider } from "../lib/auth/session-provider";
import { handshakeBelowMinCopy } from "../lib/handshake";
import { limitationCopy } from "../lib/limitations";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
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
        data: { session: { access_token: "jwt-token", user: { email: "a@b.test" } } },
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
    fetchMeta: vi.fn(async () => ({
      api_version: "1",
      sse_schema_version: "1",
      min_client_version: "9.0.0",
    })),
    fetchReady: vi.fn(async () => ({
      status: "degraded",
      query_ready: false,
      detail: "mock",
      rate_limit_degraded: false,
      dependencies: [{ name: "paradedb", status: "down" }],
    })),
    fetchMe: vi.fn(async () => ({
      user_id: "u1",
      role: "member",
      authorization_version: 1,
      upload_enabled: true,
      mfa_enrolled: true,
    })),
    listConversations: vi.fn(async () => []),
    fetchUsageMe: vi.fn(async () => ({
      scope: "me",
      cost_usd: "0",
      prompt_tokens: 0,
      completion_tokens: 0,
      usage_rows: 0,
    })),
    listCitations: vi.fn(async () => []),
  };
});

afterEach(() => {
  cleanup();
});

/**
 * Wrap ChatApp with providers.
 *
 * @param ui - Element.
 * @returns Render result.
 */
function renderChat(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>{ui}</SessionProvider>
    </QueryClientProvider>,
  );
}

describe("ChatApp Auto chrome", () => {
  it("shows Auto, blocks Send on handshake, and has no route send buttons", async () => {
    renderChat(<ChatApp />);
    const send = await screen.findByRole("button", { name: "Send" });
    expect(screen.getByRole("heading", { name: "Auto chat" })).toBeInTheDocument();
    expect(screen.getByTestId("auto-label")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hybrid" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Combined" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Inspect" })).toBeNull();
    expect(send).toBeDisabled();
    expect(screen.getAllByText(handshakeBelowMinCopy()).length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(limitationCopy("bm25_unavailable")).length,
    ).toBeGreaterThan(0);
  });
});
