/**
 * Ask surface at `/`. Composition owner for queries, run control, and chrome.
 */

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { isClassifiedApiError, type ApiFailure } from "../../lib/api";
import { HandshakeBanner } from "../auth/auth-screens";
import { useSession } from "../../lib/auth/session-provider";
import { hrefForCitationRecord } from "../../lib/citation-drawer";
import { overlaySettledTurns } from "../../lib/chat-history";
import { showSaveToQuizConvenience } from "../../lib/eval-workspace";
import { evaluatePaidHandshake } from "../../lib/handshake";
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
import { useChatRestore } from "./hooks/use-chat-restore";
import { useChatRun } from "./hooks/use-chat-run";
import { useChatSelection } from "./hooks/use-chat-selection";
import { useConversationActions, ConversationDeleteDialog } from "./hooks/use-conversation-actions";
import { useConversationScroll } from "./hooks/use-conversation-scroll";
import { toSaveToQuizSheetProps, useQuizCapture } from "./hooks/use-quiz-capture";
import { useCitationPageSource } from "./hooks/use-citation-page-source";
import { useChatPresentation } from "./hooks/use-chat-presentation";
import chatStyles from "./chat.module.css";

export { CitationDrawer } from "./citation-drawer";

/**
 * Ask: sessions, composer, transcript, diagnostics, feedback.
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
    viewingRunId: selection.viewingRunId,
    sourcesOpen: selection.sourcesOpen,
    selectedCitationId: selection.selectedCitationId,
  });
  const { compactAsk, presentationKey, reveal } =
    useChatPresentation(selection.conversationId, run.chat, run.liveRunCreated);
  const resetRun = run.resetRun;
  const resetSession = useCallback(() => resetRun("conversation-switch"), [resetRun]);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const scroll = useConversationScroll({
    conversationId: selection.conversationId,
    visibleText: reveal.visibleText,
    loadingEarlier,
    followKey: run.lastUserMessage,
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
    const error = liveQueries.currentUserError;
    return isClassifiedApiError(error) ? error.failure : null;
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
  const restore = useChatRestore({
    conversationId: selection.conversationId,
    auth: queries.auth,
    activeRunId: run.chat.runId,
    terminal: run.chat.terminal,
    historyMessages,
    viewingRunId: selection.viewingRunId,
    selectedCitationId: selection.selectedCitationId,
    liveCitations: liveQueries.citations,
    viewingCitations: liveQueries.viewingCitations,
    citationDetail: liveQueries.citationDetail,
    answerOrigin: run.chat.answerOrigin,
    setViewingRunId: selection.setViewingRunId,
    setSelectedCitationId: selection.setSelectedCitationId,
    setSourcesOpen: selection.setSourcesOpen,
  });
  const pageRunId =
    selection.viewingRunId ??
    (run.chat.terminal !== null ? run.chat.runId : null);
  const pageSource = useCitationPageSource({
    auth: liveQueries.auth,
    runId: pageRunId,
    citation: restore.selectedCitation,
    pending: liveQueries.citationDetailPending,
  });
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
    citations: [...restore.sheetCitations],
    onFillComposer: selection.fillComposer,
  });
  if (!session.ready) {
    return (
      <ChatRestoringGate
        sessionsExpanded={compactAsk || selection.sessionsExpanded}
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
        feedbackStatus={restore.feedbackStatus}
        deleteSuccess={actions.deleteSuccess}
      />
      <div className={chatStyles.mobileBar}>
        <Button type="button" variant="secondary" onClick={() => selection.setSessionsOpen(true)}>
          Sessions
        </Button>
        {restore.showSources ? (
          <Button
            type="button"
            variant="ghost"
            data-action-id="ask.sources"
            onClick={restore.openLiveSources}
          >
            Sources
          </Button>
        ) : null}
      </div>
      <ChatWorkspace
        rail={
          <ConversationRail
            {...railProps}
            expanded={compactAsk || selection.sessionsExpanded}
            onToggleExpanded={selection.toggleSessionsExpanded}
            showCollapseToggle={!compactAsk}
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
            presentationKey={presentationKey}
            onShowFullAnswer={reveal.showFullAnswer}
            citations={liveQueries.citations}
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
            {...restore.stage}
            onFillComposer={selection.fillComposer}
            composerSeed={selection.composerSeed}
            showSaveToQuiz={showSaveToQuiz}
            quiz={toSaveToQuizSheetProps(quiz, run.lastUserMessage, [...restore.sheetCitations])}
            webSearchEnabled={webSearchEnabled}
          />
        }
        sessionsExpanded={compactAsk || selection.sessionsExpanded}
      />
      {selection.conversationsOpen ? (
        <Sheet title="Sessions" side="left" onClose={() => selection.setSessionsOpen(false)}>
          <ConversationRail {...railProps} />
        </Sheet>
      ) : null}
      <CitationSheet
        open={selection.sourcesOpen}
        onClose={() => selection.setSourcesOpen(false)}
        citations={[...restore.sheetCitations]}
        pending={liveQueries.sourcesPending}
        error={liveQueries.sourcesError}
        onRetry={liveQueries.retrySources}
        hrefForCitation={hrefForCitationRecord}
        onSelectCitation={(citation, trigger) => {
          restore.handleSelectCitation(citation, trigger);
          selection.setSourcesOpen(false);
        }}
      />
      <CitationDrawer
        citation={restore.selectedCitation}
        passagePending={liveQueries.citationDetailPending}
        pageSource={pageSource}
        onClose={() => selection.setSelectedCitationId(null)}
        returnFocusRef={restore.citationTriggerRef}
      />
      <ConversationDeleteDialog
        pendingDeleteId={actions.pendingDeleteId}
        pending={actions.deletePending}
        returnFocusRef={actions.deleteTriggerRef}
        onClose={actions.cancelDelete}
        onConfirm={actions.confirmDelete}
      />
    </div>
  );
}
