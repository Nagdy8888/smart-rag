// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { sessionQueryKeys } from "../../../lib/query-keys";
import type { ConversationMessage } from "../../../lib/types";
import { useConversationActions } from "./use-conversation-actions";

const fetchConversationMessages = vi.fn();
const fetchConversation = vi.fn();
const deleteConversation = vi.fn();

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../../lib/api")>(
    "../../../lib/api",
  );
  return {
    ...actual,
    fetchConversationMessages: (...args: unknown[]) =>
      fetchConversationMessages(...args),
    fetchConversation: (...args: unknown[]) => fetchConversation(...args),
    deleteConversation: (...args: unknown[]) => deleteConversation(...args),
  };
});

const MSG_A: ConversationMessage = {
  message_id: "a-1",
  role: "user",
  content: "from A",
  created_at: "2026-08-01T00:00:00Z",
};

const MSG_B: ConversationMessage = {
  message_id: "b-1",
  role: "user",
  content: "from B",
  created_at: "2026-08-02T00:00:00Z",
};

/**
 * Wrap the action hook in a query client.
 *
 * @param children - Hook tree.
 * @returns Provider.
 */
function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useConversationActions", () => {
  beforeEach(() => {
    fetchConversationMessages.mockReset();
    fetchConversation.mockReset();
    deleteConversation.mockReset();
  });

  it("ignores a stale A page after switching to B", async () => {
    let resolveA: ((value: { items: ConversationMessage[]; next_before_id: string | null }) => void) | undefined;
    fetchConversationMessages.mockImplementation(
      (_auth: unknown, conversationId: string) => {
        if (conversationId === "conv-a") {
          return new Promise((resolve) => {
            resolveA = resolve;
          });
        }
        return Promise.resolve({ items: [MSG_B], next_before_id: null });
      },
    );
    let generation = 0;
    const { result, rerender } = renderHook(
      ({ conversationId }: { conversationId: string }) =>
        useConversationActions({
          auth: { accessToken: "jwt-token" },
          conversationId,
          keys: sessionQueryKeys("jwt-token"),
          messagesNextBeforeId: "cursor-1",
          onSelect: () => undefined,
          onDeletedCurrent: () => undefined,
          onFailure: () => undefined,
          beginPrepend: () => undefined,
          generation: () => generation,
        }),
      { wrapper, initialProps: { conversationId: "conv-a" } },
    );

    act(() => {
      void result.current.handleLoadEarlier();
    });
    generation = 1;
    rerender({ conversationId: "conv-b" });
    await act(async () => {
      resolveA?.({ items: [MSG_A], next_before_id: "stale" });
    });
    expect(result.current.olderMessages).toEqual([]);
    expect(result.current.earlierError).toBeNull();

    await act(async () => {
      await result.current.handleLoadEarlier();
    });
    expect(result.current.olderMessages).toEqual([MSG_B]);
    expect(result.current.nextBeforeId).toBeNull();
  });

  it("ignores a stale failure after an A to B switch", async () => {
    let rejectA: ((reason: Error) => void) | undefined;
    fetchConversationMessages.mockImplementation(
      (_auth: unknown, conversationId: string) => {
        if (conversationId === "conv-a") {
          return new Promise((_resolve, reject) => {
            rejectA = reject;
          });
        }
        return Promise.resolve({ items: [], next_before_id: null });
      },
    );
    let generation = 0;
    const { result, rerender } = renderHook(
      ({ conversationId }: { conversationId: string }) =>
        useConversationActions({
          auth: { accessToken: "jwt-token" },
          conversationId,
          keys: sessionQueryKeys("jwt-token"),
          messagesNextBeforeId: "cursor-1",
          onSelect: () => undefined,
          onDeletedCurrent: () => undefined,
          onFailure: () => undefined,
          beginPrepend: () => undefined,
          generation: () => generation,
        }),
      { wrapper, initialProps: { conversationId: "conv-a" } },
    );

    act(() => {
      void result.current.handleLoadEarlier();
    });
    generation = 1;
    rerender({ conversationId: "conv-b" });
    await act(async () => {
      rejectA?.(new Error("stale"));
    });
    expect(result.current.earlierError).toBeNull();
    expect(result.current.olderMessages).toEqual([]);
  });

  it("retries after a load-earlier failure", async () => {
    fetchConversationMessages
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({ items: [MSG_A], next_before_id: null });
    const { result } = renderHook(
      () =>
        useConversationActions({
          auth: { accessToken: "jwt-token" },
          conversationId: "conv-a",
          keys: sessionQueryKeys("jwt-token"),
          messagesNextBeforeId: "cursor-1",
          onSelect: () => undefined,
          onDeletedCurrent: () => undefined,
          onFailure: () => undefined,
          beginPrepend: () => undefined,
          generation: () => 0,
        }),
      { wrapper },
    );

    await act(async () => {
      await result.current.handleLoadEarlier();
    });
    expect(result.current.earlierError).toBe(
      "Could not load earlier messages. Try again.",
    );
    expect(result.current.olderMessages).toEqual([]);

    await act(async () => {
      await result.current.handleLoadEarlier();
    });
    expect(result.current.earlierError).toBeNull();
    expect(result.current.olderMessages).toEqual([MSG_A]);
  });

  it("commits an empty final page and clears the cursor", async () => {
    fetchConversationMessages.mockResolvedValue({
      items: [],
      next_before_id: null,
    });
    const { result } = renderHook(
      () =>
        useConversationActions({
          auth: { accessToken: "jwt-token" },
          conversationId: "conv-a",
          keys: sessionQueryKeys("jwt-token"),
          messagesNextBeforeId: "cursor-1",
          onSelect: () => undefined,
          onDeletedCurrent: () => undefined,
          onFailure: () => undefined,
          beginPrepend: () => undefined,
          generation: () => 0,
        }),
      { wrapper },
    );

    await act(async () => {
      await result.current.handleLoadEarlier();
    });
    expect(result.current.olderMessages).toEqual([]);
    expect(result.current.nextBeforeId).toBeNull();
    expect(result.current.earlierError).toBeNull();
  });
});
