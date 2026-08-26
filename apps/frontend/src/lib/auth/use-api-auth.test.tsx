// @vitest-environment jsdom

import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { SessionProvider } from "./session-provider";
import { useApiAuth } from "./use-api-auth";

vi.mock("./browser", () => ({
  createBrowserSupabase: () => ({
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: { access_token: "stable-token", user: { email: "a@b.test" } } },
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
 * Wrap a hook in the session provider.
 *
 * @param children - Hook tree.
 * @returns Provider.
 */
function wrapper({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}

describe("useApiAuth", () => {
  it("memoizes the auth object for an unchanged token", async () => {
    const { result, rerender } = renderHook(() => useApiAuth(), { wrapper });
    await vi.waitFor(() => {
      expect(result.current).toEqual({ accessToken: "stable-token" });
    });
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });
});
