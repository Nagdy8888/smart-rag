/**
 * Bounded persistence of the in-flight Ask run pointer.
 */

"use client";

import { useEffect, useRef } from "react";
import {
  clearChatRunPointer,
  writeChatRunPointer,
} from "../../../lib/chat-pointer";

export type PaidRunPointerInput = {
  conversationId: string | null;
  runId: string | null;
  lastSequence: number;
  terminal: string | null;
};

/**
 * Persist the latest conversation/run/sequence pointer at most once per second.
 *
 * @param input - Current run identity. Never writes tokens or answer text.
 */
export function usePaidRunPointer(input: PaidRunPointerInput): void {
  const { conversationId, runId, lastSequence, terminal } = input;
  const pointerTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastPointerWriteRef = useRef(0);
  const pendingPointerRef = useRef<{
    conversationId: string;
    runId: string;
    lastSequence: number;
  } | null>(null);

  useEffect(() => {
    function flushPointer(): void {
      if (pendingPointerRef.current !== null) {
        writeChatRunPointer(pendingPointerRef.current);
        pendingPointerRef.current = null;
        lastPointerWriteRef.current = Date.now();
      }
    }
    if (conversationId !== null && runId !== null && terminal === null) {
      pendingPointerRef.current = {
        conversationId,
        runId,
        lastSequence,
      };
      const elapsed = Date.now() - lastPointerWriteRef.current;
      if (elapsed >= 1000) {
        flushPointer();
        return;
      }
      if (pointerTimerRef.current === null) {
        pointerTimerRef.current = setTimeout(() => {
          pointerTimerRef.current = null;
          flushPointer();
        }, 1000 - elapsed);
      }
      return () => {
        if (pointerTimerRef.current !== null) {
          clearTimeout(pointerTimerRef.current);
          pointerTimerRef.current = null;
        }
      };
    }
    if (terminal !== null) {
      flushPointer();
      clearChatRunPointer();
    }
    return undefined;
  }, [conversationId, lastSequence, runId, terminal]);

  useEffect(() => {
    return () => {
      if (pointerTimerRef.current !== null) {
        clearTimeout(pointerTimerRef.current);
      }
      if (pendingPointerRef.current !== null) {
        writeChatRunPointer(pendingPointerRef.current);
      }
    };
  }, []);
}
