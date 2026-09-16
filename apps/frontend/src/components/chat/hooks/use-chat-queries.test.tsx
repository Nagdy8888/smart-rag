// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  fetchCitationDetail,
  fetchConversationMessages,
  listCitations,
} from "../../../lib/api";
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
    fetchCitationDetail: vi.fn(async () => {
      throw new Error("citation detail should not prefetch");
    }),
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

  it("does not fetch citation detail for transcript rows", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    );
    vi.mocked(fetchConversationMessages).mockResolvedValue({
      items: [
        {
          message_id: "a1",
          role: "assistant",
          content: "one",
          created_at: "t1",
          run_id: "run-a",
          citation_count: 2,
        },
        {
          message_id: "a2",
          role: "assistant",
          content: "two",
          created_at: "t2",
          run_id: "run-b",
          citation_count: 1,
        },
        {
          message_id: "a3",
          role: "assistant",
          content: "three",
          created_at: "t3",
          run_id: "run-c",
          citation_count: 3,
        },
      ],
      next_before_id: null,
    });
    renderHook(
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
      expect(fetchConversationMessages).toHaveBeenCalled();
    });
    expect(fetchCitationDetail).not.toHaveBeenCalled();
    expect(listCitations).not.toHaveBeenCalled();
  });

  it("loads one viewing list then one detail only after selection", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    );
    vi.mocked(listCitations).mockResolvedValue([
      {
        citation_id: "cite-1",
        citation_index: 0,
        chunk_id: "c1",
        provenance: {},
        source_unavailable: false,
      },
    ]);
    vi.mocked(fetchCitationDetail).mockResolvedValue({
      citation_id: "cite-1",
      citation_index: 0,
      chunk_id: "c1",
      provenance: {},
      source_unavailable: false,
      evidence_excerpt: "span",
    });
    const { rerender } = renderHook(
      ({
        viewingRunId,
        sourcesOpen,
        selectedCitationId,
      }: {
        viewingRunId: string | null;
        sourcesOpen: boolean;
        selectedCitationId: string | null;
      }) =>
        useChatQueries({
          accessToken: "jwt-token",
          conversationId: "conv-1",
          runId: null,
          terminal: false,
          viewingRunId,
          sourcesOpen,
          selectedCitationId,
        }),
      {
        wrapper,
        initialProps: {
          viewingRunId: "run-hist" as string | null,
          sourcesOpen: true,
          selectedCitationId: null as string | null,
        },
      },
    );
    await waitFor(() => {
      expect(listCitations).toHaveBeenCalledTimes(1);
    });
    expect(fetchCitationDetail).not.toHaveBeenCalled();
    rerender({
      viewingRunId: "run-hist",
      sourcesOpen: true,
      selectedCitationId: "cite-1",
    });
    await waitFor(() => {
      expect(fetchCitationDetail).toHaveBeenCalledTimes(1);
    });
    expect(listCitations).toHaveBeenCalledTimes(1);
  });
});
