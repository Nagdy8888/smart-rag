// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../auth/session-provider";
import { sessionQueryKeys } from "../query-keys";
import { useCurrentUser } from "./use-current-user";

const fetchMe = vi.fn(async () => ({
  user_id: "u1",
  email: "a@b.test",
  role: "member",
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return { ...actual, fetchMe: () => fetchMe() };
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

describe("useCurrentUser", () => {
  it("shares one /me request for two consumers", async () => {
    fetchMe.mockClear();
    const wrapper = createWrapper();
    const { result } = renderHook(
      () => {
        useCurrentUser();
        return useCurrentUser();
      },
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.currentUser?.role).toBe("member");
    });
    expect(fetchMe).toHaveBeenCalledTimes(1);
    expect(sessionQueryKeys("jwt-token").me[1]).toBe("invalid");
  });
});
