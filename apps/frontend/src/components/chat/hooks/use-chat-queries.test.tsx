// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { SessionProvider } from "../../../lib/auth/session-provider";
import { sessionQueryKeys } from "../../../lib/query-keys";
import { useChatQueries } from "./use-chat-queries";

vi.mock("../../../lib/auth/browser", () => ({
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

vi.mock("../../../lib/env", () => ({
  publicSupabaseConfig: () => ({
    url: "http://127.0.0.1:54321",
    anonKey: "anon",
  }),
  apiBaseUrl: () => "http://127.0.0.1:8000",
}));

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../../lib/api")>(
    "../../../lib/api",
  );
  return {
    ...actual,
    fetchMeta: vi.fn(async () => ({
      api_version: "1",
      sse_schema_version: "1",
      min_client_version: "0.1.0",
    })),
    fetchMe: vi.fn(async () => ({
      user_id: "u1",
      email: "a@b.test",
      role: "member",
    })),
    loadConsoleReadiness: vi.fn(async () => ({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    })),
    listConversations: vi.fn(async () => []),
    fetchConversationMessages: vi.fn(async () => ({
      items: [],
      next_before_id: null,
    })),
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

describe("useChatQueries", () => {
  it("scopes conversation messages to the session key factory", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    );
    const { result } = renderHook(
      () =>
        useChatQueries({
          accessToken: "jwt-token",
          conversationId: "conv-1",
          runId: null,
          terminal: false,
        }),
      { wrapper },
    );
    await waitFor(() => {
      expect(result.current.keys.conversationMessages("conv-1")).toEqual(
        sessionQueryKeys("jwt-token").conversationMessages("conv-1"),
      );
    });
    expect(JSON.stringify(result.current.keys)).not.toContain("jwt-token");
  });
});
