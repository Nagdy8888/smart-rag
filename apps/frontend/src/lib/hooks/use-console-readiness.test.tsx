// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../auth/session-provider";
import { sessionQueryKeys } from "../query-keys";
import { useConsoleReadiness } from "./use-console-readiness";

const loadConsoleReadiness = vi.fn(async () => ({
  status: "ok",
  query_ready: true,
  detail: "ready",
  rate_limit_degraded: false,
  dependencies: [],
}));

const fetchMe = vi.fn(async () => ({
  user_id: "u1",
  email: "a@b.test",
  role: "member",
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    fetchMe: () => fetchMe(),
    loadConsoleReadiness: () => loadConsoleReadiness(),
  };
});

vi.mock("../auth/browser", () => ({
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

vi.mock("../env", () => ({
  publicSupabaseConfig: () => ({
    url: "http://127.0.0.1:54321",
    anonKey: "anon",
  }),
  apiBaseUrl: () => "http://127.0.0.1:8000",
}));

/**
 * Provide query + session context.
 *
 * @param children - Hook tree.
 * @returns Providers.
 */
function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    );
  };
}

describe("useConsoleReadiness", () => {
  it("issues one readiness request per session-role key", async () => {
    loadConsoleReadiness.mockClear();
    fetchMe.mockClear();
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => {
        useConsoleReadiness();
        return useConsoleReadiness();
      },
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.ready?.query_ready).toBe(true);
    });
    expect(loadConsoleReadiness).toHaveBeenCalledTimes(1);
    expect(sessionQueryKeys("jwt-token").consoleReady("member")).toEqual([
      "console-ready",
      "invalid",
      "member",
    ]);
  });
});
