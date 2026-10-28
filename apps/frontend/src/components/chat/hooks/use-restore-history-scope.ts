"use client";
import { useEffect, useRef } from "react";
import type { ConversationMessage, RequestedSearchScope } from "../../../lib/types";

/** Restore recorded preference once per selected history, preserving later edits. */
export function useRestoreHistoryScope(id: string | null, pending: boolean,
  messages: readonly ConversationMessage[], activeRun: string | null,
  restore: (id: string, scope: RequestedSearchScope) => void) {
  const restored = useRef<string | null>(null);
  useEffect(() => {
    if (id === null) { restored.current = null; return; }
    if (pending || activeRun !== null || restored.current === id) return;
    const latest = [...messages].reverse().find((message) => message.requested_search_scope);
    if (latest?.requested_search_scope) {
      restore(id, latest.requested_search_scope);
      restored.current = id;
    }
  }, [id, pending, messages, activeRun, restore]);
}
