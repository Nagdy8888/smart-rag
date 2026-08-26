/**
 * Selected conversation identity and reset policy for Ask.
 */

"use client";

import { useCallback, useState } from "react";
import { useLayoutPreference } from "../../../lib/hooks/use-layout-preference";
import { SESSIONS_EXPANDED_STORAGE_KEY } from "../../../lib/layout-preferences";

export type UseChatSelectionResult = {
  conversationId: string | null;
  setConversationId: (id: string | null) => void;
  composerSeed: { text: string; key: number };
  fillComposer: (text: string) => void;
  sessionsExpanded: boolean;
  toggleSessionsExpanded: () => void;
  conversationsOpen: boolean;
  setSessionsOpen: (open: boolean) => void;
  sourcesOpen: boolean;
  setSourcesOpen: (open: boolean) => void;
  detailsOpen: boolean;
  setDetailsOpen: (open: boolean) => void;
};

/**
 * Own selected IDs and chrome toggles. Does not fetch or stream.
 *
 * @returns Selection state and reset-safe setters.
 */
export function useChatSelection(): UseChatSelectionResult {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [composerSeed, setComposerSeed] = useState({ text: "", key: 0 });
  const [sessionsExpanded, setSessionsExpanded] = useLayoutPreference(
    SESSIONS_EXPANDED_STORAGE_KEY,
    true,
  );
  const [conversationsOpen, setSessionsOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const fillComposer = useCallback((text: string) => {
    setComposerSeed((current) => ({ text, key: current.key + 1 }));
  }, []);

  const toggleSessionsExpanded = useCallback((): void => {
    setSessionsExpanded(!sessionsExpanded);
  }, [sessionsExpanded, setSessionsExpanded]);

  return {
    conversationId,
    setConversationId,
    composerSeed,
    fillComposer,
    sessionsExpanded,
    toggleSessionsExpanded,
    conversationsOpen,
    setSessionsOpen,
    sourcesOpen,
    setSourcesOpen,
    detailsOpen,
    setDetailsOpen,
  };
}
