/**
 * Session-local requested search scope for Ask. Not answer origin.
 */

"use client";

import { useCallback, useRef, useState } from "react";
import type { RequestedSearchScope } from "../../../lib/types";

const DEFAULT_SCOPE: RequestedSearchScope = "company_documents";

export type UseChatScopeResult = {
  scope: RequestedSearchScope;
  setScope: (scope: RequestedSearchScope) => void;
  bindCreatedConversation: (conversationId: string) => void;
  activateConversation: (conversationId: string) => void;
  restoreConversationScope: (
    conversationId: string,
    scope: RequestedSearchScope,
  ) => void;
  resetForNewChat: () => void;
};

/**
 * Own the Answer-source selector for the mounted browser session.
 *
 * New chats default to Company files. The conversation map is session-local
 * and is not erased on New chat. Requested scope is never treated as origin.
 *
 * @param activeConversationId - Selected conversation, or null on a blank chat.
 * @returns Selector value plus identity-transition helpers.
 */
export function useChatScope(
  activeConversationId: string | null,
): UseChatScopeResult {
  const mapRef = useRef(new Map<string, RequestedSearchScope>());
  const scopeRef = useRef<RequestedSearchScope>(DEFAULT_SCOPE);
  const [scope, setScopeState] = useState<RequestedSearchScope>(DEFAULT_SCOPE);

  const setScope = useCallback(
    (next: RequestedSearchScope) => {
      scopeRef.current = next;
      setScopeState(next);
      if (activeConversationId !== null) {
        mapRef.current.set(activeConversationId, next);
      }
    },
    [activeConversationId],
  );

  const bindCreatedConversation = useCallback((conversationId: string) => {
    mapRef.current.set(conversationId, scopeRef.current);
  }, []);

  const activateConversation = useCallback((conversationId: string) => {
    const stored = mapRef.current.get(conversationId);
    const next = stored ?? DEFAULT_SCOPE;
    if (stored === undefined) {
      mapRef.current.set(conversationId, next);
    }
    scopeRef.current = next;
    setScopeState(next);
  }, []);

  const restoreConversationScope = useCallback(
    (conversationId: string, next: RequestedSearchScope) => {
      mapRef.current.set(conversationId, next);
      scopeRef.current = next;
      setScopeState(next);
    },
    [],
  );

  const resetForNewChat = useCallback(() => {
    scopeRef.current = DEFAULT_SCOPE;
    setScopeState(DEFAULT_SCOPE);
  }, []);

  return {
    scope,
    setScope,
    bindCreatedConversation,
    activateConversation,
    restoreConversationScope,
    resetForNewChat,
  };
}
