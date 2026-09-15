/**
 * Ask surface at `/`. Composition owner for queries, run control, and chrome.
 */

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isClassifiedApiError, submitFeedback, type ApiFailure } from "../../lib/api";
import { HandshakeBanner } from "../auth/auth-screens";
import { useSession } from "../../lib/auth/session-provider";
import { hrefForCitationRecord } from "../../lib/citation-drawer";
import { overlaySettledTurns } from "../../lib/chat-history";
import { showSaveToQuizConvenience } from "../../lib/eval-workspace";
import { evaluatePaidHandshake } from "../../lib/handshake";
import { shouldShowCitations } from "../../lib/answer-origin";
import { FEEDBACK_TAGS_UP, type CitationResponse, type FeedbackTag } from "../../lib/types";
import { webSearchCapability } from "../../lib/web-search";
import { Button } from "../ui/button";
import { Sheet } from "../ui/sheet";
import { ChatBanners } from "./chat-banners";
import {
  ChatRestoringGate,
  ChatRevokedGate,
  ChatSignedOutGate,
} from "./chat-session-gate";
import { ChatStage } from "./chat-stage";
import { ChatWorkspace } from "./chat-workspace";
import { CitationDrawer } from "./citation-drawer";
import { CitationSheet } from "./citation-sheet";
import { ConversationRail } from "./conversation-rail";
import { useChatQueries } from "./hooks/use-chat-queries";
import { useChatRun } from "./hooks/use-chat-run";
import { useChatSelection } from "./hooks/use-chat-selection";
import { useConversationActions } from "./hooks/use-conversation-actions";
import { useConversationScroll } from "./hooks/use-conversation-scroll";
import { toSaveToQuizSheetProps, useQuizCapture } from "./hooks/use-quiz-capture";
import { useVerifiedAnswerReveal } from "./hooks/use-verified-answer-reveal";
import chatStyles from "./chat.module.css";

export { CitationDrawer } from "./citation-drawer";

/**
 * Ask: sessions, composer, transcript, diagnostics, feedback.
 *
 * @returns Chat surface. Fetch and SSE live in extracted hooks.
 */
export function ChatApp() {
  const session = useSession();
  const accessToken = session.accessToken;
  const selection = useChatSelection();
  const queries = useChatQueries({
    accessToken,
    conversationId: selection.conversationId,
    runId: null,
    terminal: false,
  });
  const handshake = evaluatePaidHandshake(
    queries.meta ?? null,
    queries.metaPending ? "loading" : queries.metaError ? "error" : "ok",
  );
  const webSearchEnabled = webSearchCapability(queries.meta);
  const run = useChatRun({
    auth: queries.auth,
    conversationId: selection.conversationId,
    onConversationId: selection.setConversationId,
    handshake,
    ready: queries.ready,
    webSearchEnabled,
  });
  const liveQueries = useChatQueries({
    accessToken,
    conversationId: selection.conversationId,
    runId: run.chat.runId,
    terminal: run.chat.terminal !== null,
  });
  const [reducedMotion, setReducedMotion] = useState(false);
  const [feedbackTag, setFeedbackTag] = useState<FeedbackTag>(FEEDBACK_TAGS_UP[0]);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [thumbsUp, setThumbsUp] = useState(true);
  const [selectedCitation, setSelectedCitation] = useState<CitationResponse | null>(null);
  const [feedbackStatus, setFeedbackStatus] = useState<string | null>(null);
  const [feedbackPending, setFeedbackPending] = useState(false);
  const citationTriggerRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = (): void => setReducedMotion(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  const reveal = useVerifiedAnswerReveal({
    presentationKey: `${selection.conversationId ?? "none"}:${run.chat.runId ?? "none"}`,
    authoritativeText: run.chat.answerText,
    animate: run.liveRunCreated,
    reducedMotion,
  });
  const resetRun = run.resetRun;
  const resetSession = useCallback(() => resetRun("conversation-switch"), [resetRun]);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const scroll = useConversationScroll({
    conversationId: selection.conversationId,
    visibleText: reveal.visibleText,
    loadingEarlier,
  });
  const actions = useConversationActions({
    auth: queries.auth,
    conversationId: selection.conversationId,
    keys: queries.keys,
    messagesNextBeforeId: liveQueries.messagesNextBeforeId,
    onSelect: selection.setConversationId,
    onBeginSelect: () => resetRun("select-conversation"),
    onDeletedCurrent: resetSession,
    onFailure: run.setFailure,
    beginPrepend: scroll.beginPrepend,
    generation: scroll.generation,
  });
  if (loadingEarlier !== actions.loadingEarlier) {
    setLoadingEarlier(actions.loadingEarlier);
  }
  const meFailure = useMemo((): ApiFailure | null => {
    if (liveQueries.currentUserError === null || liveQueries.currentUserError === undefined) {
      return null;
    }
    if (isClassifiedApiError(liveQueries.currentUserError)) {
      return liveQueries.currentUserError.failure;
    }
    return null;
  }, [liveQueries.currentUserError]);
  const visibleFailure = run.failure ?? meFailure;
  const meError = queries.currentUserError ?? liveQueries.currentUserError;
  const sessionRevokedNow =
    (meError instanceof Error && meError.message === "session_revoked") ||
    (visibleFailure?.kind === "auth" && visibleFailure.detail === "session_revoked");
  const [sessionRevoked, setSessionRevoked] = useState(false);
  if (sessionRevokedNow && !sessionRevoked) {
    setSessionRevoked(true);
  }
  useEffect(() => {
    if (sessionRevokedNow) {
      void session.signOut();
    }
  }, [session, sessionRevokedNow]);
  const historyMessages = useMemo(
    () =>
      overlaySettledTurns(
        [...actions.olderMessages, ...[...liveQueries.messages].reverse()],
        run.settledTurns,
      ),
    [actions.olderMessages, liveQueries.messages, run.settledTurns],
  );
  const visibleCitations = shouldShowCitations(run.chat.answerOrigin)
    ? [...liveQueries.citations]
    : [];
  const paradeDbDown =
    liveQueries.ready?.dependencies.some(
      (item) => item.name === "paradedb" && item.status === "down",
    ) === true;
  const showSaveToQuiz = showSaveToQuizConvenience(
    liveQueries.currentUser?.role,
    queries.meta,
  );
  const quiz = useQuizCapture({
    auth: queries.auth,
    enabled: showSaveToQuiz,
    runId: run.chat.runId,
    terminal: run.chat.terminal,
    question: run.lastUserMessage,
    citations: visibleCitations,
    onFillComposer: selection.fillComposer,
  });

  const sendFeedback = useCallback(async () => {
    if (queries.auth === null || run.chat.runId === null) return;
    setFeedbackPending(true);
    try {
      await submitFeedback(queries.auth, run.chat.runId, thumbsUp, feedbackTag, feedbackComment || null);
      setFeedbackStatus("Feedback recorded.");
    } catch {
      setFeedbackStatus("Feedback could not be recorded. Try again.");
    } finally {
      setFeedbackPending(false);
    }
  }, [feedbackComment, feedbackTag, queries.auth, run.chat.runId, thumbsUp]);

  const handleSelectCitation = (citation: CitationResponse, trigger: HTMLButtonElement) => {
    citationTriggerRef.current = trigger;
    setSelectedCitation(citation);
  };
  if (!session.ready) {
    return (
      <ChatRestoringGate
        sessionsExpanded={selection.sessionsExpanded}
        onToggleExpanded={selection.toggleSessionsExpanded}
      />
    );
  }
  if (sessionRevoked) {
    return <ChatRevokedGate />;
  }
  if (accessToken === null) {
    return <ChatSignedOutGate />;
  }
  const railProps = {
    conversations: liveQueries.conversations,
    selectedId: selection.conversationId,
    loading: liveQueries.conversationsPending,
    onCreate: resetSession,
    onSelect: actions.handleSelectConversation,
    onDelete: actions.handleDeleteConversation,
    deletePending: actions.deletePending,
  };

  return (
    <div className={chatStyles.page}>
      <HandshakeBanner />
      <ChatBanners
        visibleFailure={visibleFailure}
        chat={run.chat}
        disconnected={run.disconnected}
        reconnectAttempt={run.reconnectAttempt}
        reconnectExhausted={run.reconnectExhausted}
        nextRetryMs={run.nextRetryMs}
        feedbackStatus={feedbackStatus}
        deleteSuccess={actions.deleteSuccess}
      />
      <div className={chatStyles.mobileBar}>
        <Button type="button" variant="secondary" onClick={() => selection.setSessionsOpen(true)}>
          Sessions
        </Button>
        <Button
          type="button"
          variant="ghost"
          data-action-id="ask.sources"
          onClick={() => selection.setSourcesOpen(true)}
        >
          Sources
        </Button>
      </div>
      <ChatWorkspace
        rail={
          <ConversationRail
            {...railProps}
            expanded={selection.sessionsExpanded}
            onToggleExpanded={selection.toggleSessionsExpanded}
            showCollapseToggle
          />
        }
        stage={
          <ChatStage
            chat={run.chat}
            run={run}
            historyMessages={historyMessages}
            messagesPending={liveQueries.messagesPending}
            messagesError={liveQueries.messagesError}
            nextBeforeId={actions.nextBeforeId}
            loadingEarlier={actions.loadingEarlier}
            earlierError={actions.earlierError}
            onLoadEarlier={() => void actions.handleLoadEarlier()}
            visibleAnswer={reveal.visibleText}
            revealing={reveal.isRevealing}
            presentationKey={`${selection.conversationId ?? "none"}:${run.chat.runId ?? "none"}`}
            onShowFullAnswer={reveal.showFullAnswer}
            citations={visibleCitations}
            conversationRef={scroll.containerRef}
            pinned={scroll.pinned}
            onJumpToLatest={scroll.jumpToLatest}
            handshake={handshake}
            ready={liveQueries.ready}
            readyPending={liveQueries.readyPending}
            paradeDbDown={paradeDbDown}
            companyUsd={String(liveQueries.usage?.cost_usd ?? "0")}
            detailsOpen={selection.detailsOpen}
            onDetailsOpen={selection.setDetailsOpen}
            onSourcesOpen={() => selection.setSourcesOpen(true)}
            onSelectCitation={handleSelectCitation}
            onFillComposer={selection.fillComposer}
            composerSeed={selection.composerSeed}
            thumbsUp={thumbsUp}
            onThumbs={setThumbsUp}
            feedbackTag={feedbackTag}
            onTag={setFeedbackTag}
            feedbackComment={feedbackComment}
            onComment={setFeedbackComment}
            onFeedback={() => {
              void sendFeedback();
            }}
            feedbackPending={feedbackPending}
            showSaveToQuiz={showSaveToQuiz}
            quiz={toSaveToQuizSheetProps(quiz, run.lastUserMessage, visibleCitations)}
            webSearchEnabled={webSearchEnabled}
          />
        }
        sessionsExpanded={selection.sessionsExpanded}
      />
      {selection.conversationsOpen ? (
        <Sheet title="Sessions" side="left" onClose={() => selection.setSessionsOpen(false)}>
          <ConversationRail {...railProps} />
        </Sheet>
      ) : null}
      <CitationSheet
        open={selection.sourcesOpen}
        onClose={() => selection.setSourcesOpen(false)}
        citations={visibleCitations}
        hrefForCitation={(citation) => hrefForCitationRecord(citation)}
        onSelectCitation={(citation, trigger) => {
          citationTriggerRef.current = trigger;
          setSelectedCitation(citation);
          selection.setSourcesOpen(false);
        }}
      />
      <CitationDrawer
        citation={selectedCitation}
        onClose={() => setSelectedCitation(null)}
        returnFocusRef={citationTriggerRef}
      />
    </div>
  );
}
