// @vitest-environment jsdom

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useChatScope } from "./use-chat-scope";

describe("useChatScope", () => {
  it("defaults a blank chat to Auto", () => {
    const { result } = renderHook(() => useChatScope(null));
    expect(result.current.scope).toBe("auto");
  });

  it("keeps the pre-send selection when a conversation is created", () => {
    const { result } = renderHook(() => useChatScope(null));
    act(() => {
      result.current.setScope("general_knowledge");
      result.current.bindCreatedConversation("conv-1");
      result.current.activateConversation("conv-1");
    });
    expect(result.current.scope).toBe("general_knowledge");
  });

  it("restores per-conversation scope and resets New chat without erasing the map", () => {
    const { result } = renderHook(() => useChatScope("conv-a"));
    act(() => {
      result.current.setScope("general_knowledge");
      result.current.activateConversation("conv-b");
    });
    expect(result.current.scope).toBe("auto");
    act(() => {
      result.current.activateConversation("conv-a");
    });
    expect(result.current.scope).toBe("general_knowledge");
    act(() => {
      result.current.restoreConversationScope("conv-b", "auto");
    });
    expect(result.current.scope).toBe("auto");
    act(() => {
      result.current.resetForNewChat();
    });
    expect(result.current.scope).toBe("auto");
    act(() => {
      result.current.activateConversation("conv-a");
    });
    expect(result.current.scope).toBe("general_knowledge");
  });

  it("keeps Web selected when the server flag is off", () => {
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useChatScope("conv-web", enabled),
      { initialProps: { enabled: true } },
    );
    act(() => {
      result.current.restoreConversationScope("conv-web", "web");
    });
    expect(result.current.scope).toBe("web");
    rerender({ enabled: false });
    expect(result.current.scope).toBe("web");
    act(() => {
      result.current.setScope("web");
    });
    expect(result.current.scope).toBe("web");
  });
});
