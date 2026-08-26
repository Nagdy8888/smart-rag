// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, act } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { useChatRun } from "./use-chat-run";

/**
 * Wrap the run hook in a query client.
 *
 * @param children - Hook tree.
 * @returns Provider.
 */
function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useChatRun", () => {
  it("resets local run state without inventing a terminal", () => {
    const { result } = renderHook(
      () =>
        useChatRun({
          auth: { accessToken: "jwt-token" },
          conversationId: "conv-1",
          onConversationId: () => undefined,
          handshake: {
            allowPaidPost: true,
            kind: "ok",
            minClientVersion: "0.1.0",
            sseSchemaVersion: "1",
          },
          ready: {
            status: "ok",
            query_ready: true,
            detail: "ready",
            rate_limit_degraded: false,
            dependencies: [],
          },
        }),
      { wrapper },
    );
    expect(result.current.chat.terminal).toBeNull();
    act(() => {
      result.current.resetRun("conversation-switch");
    });
    expect(result.current.chat.terminal).toBeNull();
    expect(result.current.sending).toBe(false);
  });
});
