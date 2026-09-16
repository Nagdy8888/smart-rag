/**
 * Restore identities, Sources selection, and feedback targeting for Ask.
 */

"use client";

import { useCallback, useMemo, useRef, useState, type RefObject } from "react";
import { submitFeedback, type ApiAuth } from "../../../lib/api";
import {
  citationsForSources,
  feedbackTargetRunId,
  latestSettledRunId,
  selectedCitationRecord,
  showSourcesControl,
} from "../../../lib/chat-restore";
import {
  FEEDBACK_TAGS_UP,
  type CitationResponse,
  type ConversationMessage,
  type FeedbackTag,
} from "../../../lib/types";

export type UseChatRestoreInput = {
  conversationId: string | null;
  auth: ApiAuth | null;
  activeRunId: string | null;
  terminal: string | null;
  historyMessages: readonly ConversationMessage[];
  viewingRunId: string | null;
  selectedCitationId: string | null;
  liveCitations: readonly CitationResponse[];
  viewingCitations: readonly CitationResponse[];
  citationDetail: CitationResponse | null;
  answerOrigin: string | null;
  setViewingRunId: (id: string | null) => void;
  setSelectedCitationId: (id: string | null) => void;
  setSourcesOpen: (open: boolean) => void;
};

export type UseChatRestoreResult = {
  feedbackRunId: string | null;
  sheetCitations: readonly CitationResponse[];
  selectedCitation: CitationResponse | null;
  showSources: boolean;
  sourcesCount: number;
  citationTriggerRef: RefObject<HTMLElement | null>;
  handleSelectCitation: (
    citation: CitationResponse,
    trigger: HTMLButtonElement,
  ) => void;
  openTurnSources: (runId: string) => void;
  openLiveSources: () => void;
  thumbsUp: boolean;
  setThumbsUp: (value: boolean) => void;
  feedbackTag: FeedbackTag;
  setFeedbackTag: (tag: FeedbackTag) => void;
  feedbackComment: string;
  setFeedbackComment: (value: string) => void;
  feedbackStatus: string | null;
  feedbackPending: boolean;
  sendFeedback: () => Promise<void>;
  stage: {
    onSourcesOpen: () => void;
    onSelectCitation: (
      citation: CitationResponse,
      trigger: HTMLButtonElement,
    ) => void;
    onOpenTurnSources: (runId: string) => void;
    showSources: boolean;
    sourcesCount: number;
    feedbackRunId: string | null;
    thumbsUp: boolean;
    onThumbs: (value: boolean) => void;
    feedbackTag: FeedbackTag;
    onTag: (tag: FeedbackTag) => void;
    feedbackComment: string;
    onComment: (value: string) => void;
    onFeedback: () => void;
    feedbackPending: boolean;
  };
};

/**
 * Own restore/feedback/citation-select so ChatApp stays within budget.
 *
 * Feedback never uses a reconnect pointer while `terminal` is null.
 * Historical `viewingRunId` is not written to the live run pointer.
 *
 * @param input - Live run, transcript, and selection setters.
 * @returns Sources/feedback bindings for ChatApp and ChatStage.
 */
export function useChatRestore(input: UseChatRestoreInput): UseChatRestoreResult {
  const {
    conversationId,
    auth,
    activeRunId,
    terminal,
    historyMessages,
    viewingRunId,
    selectedCitationId,
    liveCitations,
    viewingCitations,
    citationDetail,
    answerOrigin,
    setViewingRunId,
    setSelectedCitationId,
    setSourcesOpen,
  } = input;
  const [feedbackStore, setFeedbackStore] = useState({
    key: conversationId,
    tag: FEEDBACK_TAGS_UP[0] as FeedbackTag,
    comment: "",
    thumbsUp: true,
    status: null as string | null,
    pending: false,
  });
  const citationTriggerRef = useRef<HTMLElement | null>(null);
  const feedback = useMemo(
    () =>
      feedbackStore.key === conversationId
        ? feedbackStore
        : {
            key: conversationId,
            tag: FEEDBACK_TAGS_UP[0] as FeedbackTag,
            comment: "",
            thumbsUp: true,
            status: null,
            pending: false,
          },
    [conversationId, feedbackStore],
  );
  const setFeedbackTag = useCallback(
    (tag: FeedbackTag) => {
      setFeedbackStore({ ...feedback, key: conversationId, tag });
    },
    [conversationId, feedback],
  );
  const setFeedbackComment = useCallback(
    (comment: string) => {
      setFeedbackStore({ ...feedback, key: conversationId, comment });
    },
    [conversationId, feedback],
  );
  const setThumbsUp = useCallback(
    (thumbsUp: boolean) => {
      setFeedbackStore({ ...feedback, key: conversationId, thumbsUp });
    },
    [conversationId, feedback],
  );
  const settledRunId = latestSettledRunId(historyMessages);
  const feedbackRunId = feedbackTargetRunId(
    activeRunId,
    terminal,
    viewingRunId,
    settledRunId,
  );
  const liveVisible = showSourcesControl(answerOrigin, null) ? liveCitations : [];
  const sheetCitations = citationsForSources(
    viewingRunId,
    activeRunId,
    liveVisible,
    viewingCitations,
  );
  const selectedCitation = selectedCitationRecord(
    sheetCitations,
    selectedCitationId,
    citationDetail,
  );

  const handleSelectCitation = useCallback(
    (citation: CitationResponse, trigger: HTMLButtonElement) => {
      citationTriggerRef.current = trigger;
      setSelectedCitationId(citation.citation_id);
    },
    [setSelectedCitationId],
  );
  const openTurnSources = useCallback(
    (runId: string) => {
      setViewingRunId(runId);
      setSelectedCitationId(null);
      setSourcesOpen(true);
    },
    [setSelectedCitationId, setSourcesOpen, setViewingRunId],
  );
  const openLiveSources = useCallback(() => {
    setViewingRunId(null);
    setSourcesOpen(true);
  }, [setSourcesOpen, setViewingRunId]);
  const sendFeedback = useCallback(async () => {
    if (auth === null || feedbackRunId === null) {
      return;
    }
    setFeedbackStore({ ...feedback, key: conversationId, pending: true });
    try {
      await submitFeedback(
        auth,
        feedbackRunId,
        feedback.thumbsUp,
        feedback.tag,
        feedback.comment || null,
      );
      setFeedbackStore({
        ...feedback,
        key: conversationId,
        pending: false,
        status: "Feedback recorded.",
      });
    } catch {
      setFeedbackStore({
        ...feedback,
        key: conversationId,
        pending: false,
        status: "Feedback could not be recorded. Try again.",
      });
    }
  }, [auth, conversationId, feedback, feedbackRunId]);

  return {
    feedbackRunId,
    sheetCitations,
    selectedCitation,
    showSources: showSourcesControl(answerOrigin, viewingRunId),
    sourcesCount: sheetCitations.length,
    citationTriggerRef,
    handleSelectCitation,
    openTurnSources,
    openLiveSources,
    thumbsUp: feedback.thumbsUp,
    setThumbsUp,
    feedbackTag: feedback.tag,
    setFeedbackTag,
    feedbackComment: feedback.comment,
    setFeedbackComment,
    feedbackStatus: feedback.status,
    feedbackPending: feedback.pending,
    sendFeedback,
    stage: {
      onSourcesOpen: openLiveSources,
      onSelectCitation: handleSelectCitation,
      onOpenTurnSources: openTurnSources,
      showSources: showSourcesControl(answerOrigin, viewingRunId),
      sourcesCount: sheetCitations.length,
      feedbackRunId,
      thumbsUp: feedback.thumbsUp,
      onThumbs: setThumbsUp,
      feedbackTag: feedback.tag,
      onTag: setFeedbackTag,
      feedbackComment: feedback.comment,
      onComment: setFeedbackComment,
      onFeedback: () => {
        void sendFeedback();
      },
      feedbackPending: feedback.pending,
    },
  };
}
