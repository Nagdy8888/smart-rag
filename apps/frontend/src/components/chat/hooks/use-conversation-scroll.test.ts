// @vitest-environment jsdom

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  CONVERSATION_PIN_THRESHOLD_PX,
  isPinnedToBottom,
  useConversationScroll,
} from "./use-conversation-scroll";

function attachScroller(
  ref: { current: HTMLDivElement | null },
  metrics: { scrollHeight: number; clientHeight: number; scrollTop: number },
): HTMLDivElement {
  const element = document.createElement("div");
  Object.defineProperty(element, "scrollHeight", {
    get: () => metrics.scrollHeight,
    configurable: true,
  });
  Object.defineProperty(element, "clientHeight", {
    get: () => metrics.clientHeight,
    configurable: true,
  });
  Object.defineProperty(element, "scrollTop", {
    get: () => metrics.scrollTop,
    set: (value: number) => {
      metrics.scrollTop = value;
    },
    configurable: true,
  });
  ref.current = element;
  document.body.appendChild(element);
  return element;
}

describe("isPinnedToBottom", () => {
  afterEach(() => {
    cleanup();
    document.body.replaceChildren();
  });

  it("pins at the 48px threshold and unpins above it", () => {
    const element = document.createElement("div");
    Object.defineProperty(element, "scrollHeight", { value: 400 });
    Object.defineProperty(element, "clientHeight", { value: 200 });
    Object.defineProperty(element, "scrollTop", {
      value: 400 - 200 - CONVERSATION_PIN_THRESHOLD_PX,
      writable: true,
    });
    expect(isPinnedToBottom(element)).toBe(true);
    Object.defineProperty(element, "scrollTop", {
      value: 400 - 200 - CONVERSATION_PIN_THRESHOLD_PX - 1,
      writable: true,
    });
    expect(isPinnedToBottom(element)).toBe(false);
  });
});

describe("useConversationScroll", () => {
  afterEach(() => {
    cleanup();
    document.body.replaceChildren();
  });

  it("scrolls on reveal growth only while pinned and jump re-pins", () => {
    const metrics = { scrollHeight: 400, clientHeight: 200, scrollTop: 152 };
    const { result, rerender } = renderHook(
      (props: { text: string; conversationId: string | null }) =>
        useConversationScroll({
          conversationId: props.conversationId,
          visibleText: props.text,
          loadingEarlier: false,
        }),
      { initialProps: { text: "Hi", conversationId: "c1" } },
    );
    attachScroller(result.current.containerRef, metrics);
    rerender({ text: "Hi there", conversationId: "c1" });
    expect(metrics.scrollTop).toBe(400);
    metrics.scrollTop = 0;
    act(() => {
      result.current.containerRef.current?.dispatchEvent(
        new WheelEvent("wheel", { deltaY: -40 }),
      );
    });
    expect(result.current.pinned).toBe(false);
    metrics.scrollHeight = 800;
    rerender({ text: "Hi there verified more", conversationId: "c1" });
    expect(metrics.scrollTop).toBe(0);
    act(() => {
      result.current.jumpToLatest();
    });
    expect(result.current.pinned).toBe(true);
    expect(metrics.scrollTop).toBe(800);
  });

  it("restores the prepend anchor and ignores a stale conversation generation", () => {
    const metrics = { scrollHeight: 400, clientHeight: 200, scrollTop: 80 };
    const { result, rerender } = renderHook(
      (props: {
        conversationId: string | null;
        loadingEarlier: boolean;
        text: string;
      }) =>
        useConversationScroll({
          conversationId: props.conversationId,
          visibleText: props.text,
          loadingEarlier: props.loadingEarlier,
        }),
      {
        initialProps: {
          conversationId: "c1",
          loadingEarlier: false,
          text: "",
        },
      },
    );
    attachScroller(result.current.containerRef, metrics);
    const firstGeneration = result.current.generation();
    act(() => {
      result.current.beginPrepend();
    });
    rerender({ conversationId: "c1", loadingEarlier: true, text: "" });
    metrics.scrollHeight = 700;
    rerender({ conversationId: "c1", loadingEarlier: false, text: "" });
    expect(metrics.scrollTop).toBe(80 + 300);
    rerender({ conversationId: "c2", loadingEarlier: false, text: "" });
    expect(result.current.generation()).toBe(firstGeneration + 1);
    expect(result.current.pinned).toBe(true);
  });
});
