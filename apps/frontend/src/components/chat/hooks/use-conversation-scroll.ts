/**
 * Pin the conversation pane to incoming verified text unless the user scrolls away.
 */

"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";

/** Distance from the bottom that still counts as pinned, in CSS pixels. */
export const CONVERSATION_PIN_THRESHOLD_PX = 48;

export type UseConversationScrollInput = {
  conversationId: string | null;
  visibleText: string;
  loadingEarlier: boolean;
  /** Changes when a new live question is submitted. Scrolls if still pinned. */
  followKey?: string;
};

export type UseConversationScrollResult = {
  containerRef: RefObject<HTMLDivElement | null>;
  pinned: boolean;
  jumpToLatest(): void;
  beginPrepend(): void;
  generation(): number;
};

/**
 * Return whether the container is within the pin threshold of its bottom.
 *
 * @param element - Conversation scroller.
 * @returns True when the remaining distance is ≤ 48px.
 */
export function isPinnedToBottom(element: HTMLElement): boolean {
  return (
    element.scrollHeight - element.scrollTop - element.clientHeight <=
    CONVERSATION_PIN_THRESHOLD_PX
  );
}

/**
 * Follow visible answer growth and a new live question only while the user
 * remains near the bottom.
 *
 * Never scrolls `window`, `#main`, or the session rail. `useLayoutEffect` is
 * used only to restore the prepended-history anchor in the same frame as the
 * DOM mutation so the viewport does not jump.
 *
 * @param input - Conversation id, visible text, live-question key, and pagination flag.
 * @returns Container ref, pin state, and prepend helpers.
 */
export function useConversationScroll(
  input: UseConversationScrollInput,
): UseConversationScrollResult {
  const { conversationId, visibleText, loadingEarlier, followKey = "" } = input;
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [pinned, setPinned] = useState(true);
  const pinnedRef = useRef(true);
  const generationRef = useRef(0);
  const conversationRef = useRef(conversationId);
  const prependHeightRef = useRef<number | null>(null);
  const wasLoadingRef = useRef(false);

  useEffect(() => {
    if (conversationRef.current === conversationId) {
      return;
    }
    conversationRef.current = conversationId;
    generationRef.current += 1;
    prependHeightRef.current = null;
    pinnedRef.current = true;
    setPinned(true);
  }, [conversationId]);

  useEffect(() => {
    const element = containerRef.current;
    if (element === null) {
      return;
    }
    const syncPin = (): void => {
      const next = isPinnedToBottom(element);
      if (next !== pinnedRef.current) {
        pinnedRef.current = next;
        setPinned(next);
      }
    };
    const onWheel = (event: WheelEvent): void => {
      if (event.deltaY < 0) {
        pinnedRef.current = false;
        setPinned(false);
      }
    };
    const onTouch = (): void => {
      if (!isPinnedToBottom(element)) {
        pinnedRef.current = false;
        setPinned(false);
      }
    };
    element.addEventListener("scroll", syncPin, { passive: true });
    element.addEventListener("wheel", onWheel, { passive: true });
    element.addEventListener("touchmove", onTouch, { passive: true });
    return () => {
      element.removeEventListener("scroll", syncPin);
      element.removeEventListener("wheel", onWheel);
      element.removeEventListener("touchmove", onTouch);
    };
  }, [conversationId, visibleText]);

  useEffect(() => {
    const element = containerRef.current;
    if (element === null || !pinnedRef.current) {
      return;
    }
    element.scrollTop = element.scrollHeight;
  }, [visibleText, followKey]);

  useLayoutEffect(() => {
    // Restore the pre-prepend scroll anchor in the same frame as the inserted
    // history nodes so the user keeps their place after Load earlier.
    if (loadingEarlier) {
      wasLoadingRef.current = true;
      return;
    }
    if (!wasLoadingRef.current) {
      return;
    }
    wasLoadingRef.current = false;
    const element = containerRef.current;
    const captured = prependHeightRef.current;
    if (element === null || captured === null) {
      return;
    }
    element.scrollTop += element.scrollHeight - captured;
    prependHeightRef.current = null;
  }, [loadingEarlier]);

  const jumpToLatest = useCallback(() => {
    pinnedRef.current = true;
    setPinned(true);
    const element = containerRef.current;
    if (element !== null) {
      element.scrollTop = element.scrollHeight;
    }
  }, []);

  const beginPrepend = useCallback(() => {
    const element = containerRef.current;
    prependHeightRef.current = element?.scrollHeight ?? 0;
  }, []);

  const generation = useCallback(() => generationRef.current, []);

  return {
    containerRef,
    pinned,
    jumpToLatest,
    beginPrepend,
    generation,
  };
}
