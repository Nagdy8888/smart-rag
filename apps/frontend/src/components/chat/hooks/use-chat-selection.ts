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
  viewingRunId: string | null;
  setViewingRunId: (id: string | null) => void;
  selectedCitationId: string | null;
  setSelectedCitationId: (id: string | null) => void;
};

/**
 * Own selected IDs and chrome toggles. Does not fetch or stream.
 *
 * Conversation changes clear viewing/citation/source restore state. They
 * never write a historical run into the reconnect pointer.
 *
 * @returns Selection state and reset-safe setters.
 */
export function useChatSelection(): UseChatSelectionResult {
  const [conversationId, setConversationIdState] = useState<string | null>(null);
  const [composerSeed, setComposerSeed] = useState({ text: "", key: 0 });
  const [sessionsExpanded, setSessionsExpanded] = useLayoutPreference(
    SESSIONS_EXPANDED_STORAGE_KEY,
    true,
  );
  const [conversationsOpen, setSessionsOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [viewingRunId, setViewingRunId] = useState<string | null>(null);
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(
    null,
  );

  const fillComposer = useCallback((text: string) => {
    setComposerSeed((current) => ({ text, key: current.key + 1 }));
  }, []);

  const toggleSessionsExpanded = useCallback((): void => {
    setSessionsExpanded(!sessionsExpanded);
  }, [sessionsExpanded, setSessionsExpanded]);

  const setConversationId = useCallback((id: string | null) => {
    setConversationIdState(id);
    setViewingRunId(null);
    setSelectedCitationId(null);
    setSourcesOpen(false);
  }, []);

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
    viewingRunId,
    setViewingRunId,
    selectedCitationId,
    setSelectedCitationId,
  };
}
