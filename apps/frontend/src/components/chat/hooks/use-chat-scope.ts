/**
 * Session-local requested search scope for Ask. Not answer origin.
 */

"use client";

import { useCallback, useRef, useState } from "react";
import type { RequestedSearchScope } from "../../../lib/types";
import { visibleRequestedSearchScope } from "../../../lib/web-search";

const DEFAULT_SCOPE: RequestedSearchScope = "auto";

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
 * New chats default to Auto. The conversation map is session-local and is
 * not erased on New chat. Requested scope is never treated as origin.
 * Web remains selectable when `/api/meta` `web_search_enabled` is false;
 * the API still refuses unauthorized Web admits.
 *
 * @param activeConversationId - Selected conversation, or null on a blank chat.
 * @param webSearchEnabled - `/api/meta` `web_search_enabled`. Default false.
 * @returns Selector value plus identity-transition helpers.
 */
export function useChatScope(
  activeConversationId: string | null,
  webSearchEnabled = false,
): UseChatScopeResult {
  const mapRef = useRef(new Map<string, RequestedSearchScope>());
  const scopeRef = useRef<RequestedSearchScope>(DEFAULT_SCOPE);
  const [scope, setScopeState] = useState<RequestedSearchScope>(DEFAULT_SCOPE);

  const applyScope = useCallback(
    (next: RequestedSearchScope, conversationId: string | null) => {
      const allowed = visibleRequestedSearchScope(next, webSearchEnabled);
      scopeRef.current = allowed;
      setScopeState(allowed);
      if (conversationId !== null) {
        mapRef.current.set(conversationId, allowed);
      }
    },
    [webSearchEnabled],
  );

  const setScope = useCallback(
    (next: RequestedSearchScope) => {
      applyScope(next, activeConversationId);
    },
    [activeConversationId, applyScope],
  );

  const bindCreatedConversation = useCallback((conversationId: string) => {
    mapRef.current.set(conversationId, scopeRef.current);
  }, []);

  const activateConversation = useCallback(
    (conversationId: string) => {
      const stored = mapRef.current.get(conversationId);
      applyScope(stored ?? DEFAULT_SCOPE, conversationId);
    },
    [applyScope],
  );

  const restoreConversationScope = useCallback(
    (conversationId: string, next: RequestedSearchScope) => {
      applyScope(next, conversationId);
    },
    [applyScope],
  );

  const resetForNewChat = useCallback(() => {
    applyScope(DEFAULT_SCOPE, null);
  }, [applyScope]);

  return {
    scope,
    setScope,
    bindCreatedConversation,
    activateConversation,
    restoreConversationScope,
    resetForNewChat,
  };
}
