/**
 * Ask answer column: transcript, progress, composer, and prompt chips.
 */

"use client";

import { useMemo, type RefObject } from "react";
import { shouldShowCitations } from "../../lib/answer-origin";
import { hrefForCitationRecord } from "../../lib/citation-drawer";
import type { ChatViewState } from "../../lib/chat-view";
import { paidSendBlockReason, type HandshakeDecision } from "../../lib/handshake";
import {
  isGraphOnlyInspectionRoute,
  limitationCopy,
  limitationTone,
} from "../../lib/limitations";
import { MAX_RECONNECT_ATTEMPTS } from "../../lib/stream-reconnect";
import type { CitationResponse, ConversationMessage, ReadinessResponse } from "../../lib/types";
import { SEARCH_SCOPE_LABELS, isRequestedSearchScope } from "../../lib/types";
import { visibleSearchScopes } from "../../lib/web-search";
import { Button } from "../ui/button";
import { LimitationCallout } from "../ui/limitation-callout";
import { AnswerFormatGallery } from "./answer-format-gallery";
import { AnswerSurface } from "./answer-surface";
import { ChatComposer } from "./chat-composer";
import { FeedbackPopover } from "./feedback-popover";
import { SaveToQuizSheet, type SaveToQuizSheetProps } from "./save-to-quiz-sheet";
import type { UseChatRunResult } from "./hooks/use-chat-run";
import { RunDetailsSheet } from "./run-details-sheet";
import type { FeedbackTag } from "../../lib/types";
import chatStyles from "./chat-transcript.module.css";

/**
 * Live Ask chips that tend to return code or tables from the company PDF.
 * The format gallery above shows rendering without sending.
 */
const PROMPT_CHIPS = [
  "Reproduce the cancel_order tool as a fenced Python code block from Building Applications with AI Agents.",
  "Reproduce Table 10-3 (RACI matrix of monitoring metrics) as a Markdown pipe table from Building Applications with AI Agents.",
  "Reproduce Table 2-1 (Selected open weight models) as a Markdown pipe table from Building Applications with AI Agents.",
] as const;

export type ChatStageProps = {
  chat: ChatViewState;
  run: UseChatRunResult;
  historyMessages: ConversationMessage[];
  /** True while the selected conversation transcript is fetching. */
  messagesPending?: boolean;
  /** True when the selected transcript query failed. */
  messagesError?: boolean;
  nextBeforeId: string | null;
  loadingEarlier: boolean;
  earlierError: string | null;
  onLoadEarlier: () => void;
  visibleAnswer: string;
  revealing: boolean;
  presentationKey: string;
  onShowFullAnswer: () => void;
  citations: readonly CitationResponse[];
  conversationRef: RefObject<HTMLDivElement | null>;
  pinned: boolean;
  onJumpToLatest: () => void;
  handshake: HandshakeDecision;
  ready: ReadinessResponse | null;
  readyPending: boolean;
  paradeDbDown: boolean;
  companyUsd: string;
  detailsOpen: boolean;
  onDetailsOpen: (open: boolean) => void;
  onSourcesOpen: () => void;
  onSelectCitation: (citation: CitationResponse, trigger: HTMLButtonElement) => void;
  /** Open Sources for one historical owned run. */
  onOpenTurnSources?: (runId: string) => void;
  /** False hides header/mobile Sources (general origin with count 0). */
  showSources?: boolean;
  /** Header Sources count. Defaults to the live citation list length. */
  sourcesCount?: number;
  /** Settled run to POST feedback to. Null hides Give feedback. */
  feedbackRunId?: string | null;
  onFillComposer: (text: string) => void;
  composerSeed: { text: string; key: number };
  thumbsUp: boolean;
  onThumbs: (value: boolean) => void;
  feedbackTag: FeedbackTag;
  onTag: (tag: FeedbackTag) => void;
  feedbackComment: string;
  onComment: (value: string) => void;
  onFeedback: () => void;
  feedbackPending: boolean;
  showSaveToQuiz?: boolean;
  quiz?: SaveToQuizSheetProps | null;
  /** `/api/meta` Web flag. Chrome always lists Web; the API still authorizes. */
  webSearchEnabled?: boolean;
};

/**
 * Compose the live answer column.
 *
 * @param props - Run view, transcript, composer bindings, and Web flag.
 * @returns Stage section.
 */
export function ChatStage(props: ChatStageProps) {
  const {
    chat,
    run,
    historyMessages,
    messagesPending = false,
    messagesError = false,
    nextBeforeId,
    loadingEarlier,
    earlierError,
    onLoadEarlier,
    visibleAnswer,
    revealing,
    presentationKey,
    onShowFullAnswer,
    citations,
    conversationRef,
    pinned,
    onJumpToLatest,
    handshake,
    ready,
    readyPending,
    paradeDbDown,
    companyUsd,
    detailsOpen,
    onDetailsOpen,
    onSourcesOpen,
    onSelectCitation,
    onOpenTurnSources,
    showSources = true,
    sourcesCount,
    feedbackRunId = null,
    onFillComposer,
    composerSeed,
    thumbsUp,
    onThumbs,
    feedbackTag,
    onTag,
    feedbackComment,
    onComment,
    onFeedback,
    feedbackPending,
    showSaveToQuiz = false,
    quiz = null,
    webSearchEnabled = false,
  } = props;
  const running = chat.terminal === null && chat.runId !== null;
  const sendBlockReason = paidSendBlockReason(
    handshake,
    readyPending ? undefined : ready,
    chat,
  );
  const visibleCitations = shouldShowCitations(chat.answerOrigin) ? [...citations] : [];
  const headerCount = sourcesCount ?? visibleCitations.length;
  const showEmptyPrompts =
    !messagesPending &&
    !messagesError &&
    run.lastUserMessage === "" &&
    chat.answerText === "" &&
    historyMessages.length === 0;
  const bm25Limitation = chat.diagnostics.limitationCodes.includes("bm25_unavailable");
  const hrefForCitation = useMemo(
    () => (citation: CitationResponse) => hrefForCitationRecord(citation),
    [],
  );
  const scopeOptions = visibleSearchScopes(webSearchEnabled);

  return (
    <section className={chatStyles.stage} aria-label="Answer">
      <div className={chatStyles.stageHeader}>
        <div className={chatStyles.row}>
          <div
            className={chatStyles.scopeField}
            role="radiogroup"
            aria-label="Answer source"
            data-action-id="ask.scope"
            data-testid="answer-source"
            data-value={run.searchScope}
          >
            {scopeOptions.map((scope) => {
              const selected = run.searchScope === scope;
              const scopeLocked =
                run.sending || (chat.runId !== null && chat.terminal === null);
              return (
                <button
                  key={scope}
                  type="button"
                  role="radio"
                  className={chatStyles.scopeSegment}
                  aria-checked={selected}
                  data-selected={selected ? "true" : "false"}
                  data-scope={scope}
                  disabled={scopeLocked}
                  onClick={() => {
                    if (isRequestedSearchScope(scope)) {
                      run.setSearchScope(scope);
                    }
                  }}
                >
                  {SEARCH_SCOPE_LABELS[scope]}
                </button>
              );
            })}
          </div>
          {showSources ? (
            <Button
              type="button"
              variant="ghost"
              data-action-id="ask.sources"
              onClick={onSourcesOpen}
            >
              Sources ({String(headerCount)})
            </Button>
          ) : null}
          {historyMessages.length > 0 && chat.runId === null ? null : <RunDetailsSheet
            open={detailsOpen}
            onOpen={() => onDetailsOpen(true)}
            onClose={() => onDetailsOpen(false)}
            chat={chat}
            companyUsd={companyUsd}
          />}
        </div>
      </div>
      <div
        ref={conversationRef}
        className={chatStyles.conversation}
        role="region"
        aria-label="Conversation"
        tabIndex={0}
      >
        <AnswerSurface
          messages={historyMessages}
          messagesPending={messagesPending}
          messagesError={messagesError}
          hasEarlier={nextBeforeId !== null}
          onLoadEarlier={onLoadEarlier}
          loadingEarlier={loadingEarlier}
          loadEarlierError={earlierError}
          question={run.lastUserMessage}
          answer={chat.answerText}
          visibleAnswer={visibleAnswer}
          presentationKey={presentationKey}
          revealing={revealing}
          onShowFullAnswer={onShowFullAnswer}
          citations={visibleCitations}
          terminal={chat.terminal}
          answerOrigin={chat.answerOrigin}
          effectiveRoute={chat.diagnostics.effectiveRoute ?? chat.routeFamily}
          progressItems={chat.progress.items}
          starting={run.sending && chat.runId === null}
          verificationCompleted={chat.progress.verificationCompleted}
          chat={chat}
          hrefForCitation={hrefForCitation}
          onSelectCitation={onSelectCitation}
          onOpenTurnSources={onOpenTurnSources}
          promptTokens={chat.diagnostics.promptTokens}
          completionTokens={chat.diagnostics.completionTokens}
        />
        {pinned ? null : (
          <Button
            type="button"
            variant="secondary"
            className={chatStyles.jumpLatest}
            data-action-id="ask.jump_to_latest"
            onClick={onJumpToLatest}
          >
            Jump to latest
          </Button>
        )}
        {isGraphOnlyInspectionRoute(
          chat.diagnostics.effectiveRoute ?? chat.routeFamily,
        ) ? (
          <LimitationCallout tone="warning">
            Graph-only inspection is not an answering mode. Final answers use
            Hybrid evidence.
          </LimitationCallout>
        ) : null}
        {chat.diagnostics.limitationCodes.map((code) => (
          <LimitationCallout key={code} tone={limitationTone(code)}>
            {limitationCopy(code)}
          </LimitationCallout>
        ))}
        {paradeDbDown ? (
          <LimitationCallout tone="warning">
            {limitationCopy("bm25_unavailable")}
          </LimitationCallout>
        ) : null}
        {paradeDbDown && bm25Limitation ? (
          <p className={chatStyles.muted}>
            Search is degraded. Keyword retrieval is not claimed healthy.
          </p>
        ) : null}
        {showEmptyPrompts ? (
          <div className={chatStyles.emptyPrompts}>
            <AnswerFormatGallery />
            <p className={chatStyles.emptyPromptsLabel}>
              Or ask the company document
            </p>
            {PROMPT_CHIPS.map((chip) => (
              <Button
                key={chip}
                type="button"
                variant="secondary"
                data-action-id="ask.prompt_fill"
                onClick={() => onFillComposer(chip)}
              >
                {chip}
              </Button>
            ))}
          </div>
        ) : null}
        {feedbackRunId !== null ||
        (showSaveToQuiz && quiz !== null && chat.terminal !== null) ? (
          <div className={chatStyles.answerFooter}>
            {feedbackRunId !== null ? (
              <FeedbackPopover
                thumbsUp={thumbsUp}
                onThumbs={onThumbs}
                tag={feedbackTag}
                onTag={onTag}
                comment={feedbackComment}
                onComment={onComment}
                onSubmit={onFeedback}
                pending={feedbackPending}
              />
            ) : null}
            {showSaveToQuiz && quiz && chat.terminal !== null ? (
              <SaveToQuizSheet {...quiz} />
            ) : null}
          </div>
        ) : null}
      </div>
      <ChatComposer
        onSubmit={run.send}
        disabled={sendBlockReason !== null}
        sending={run.sending}
        running={running}
        onStop={() => {
          void run.cancel();
        }}
        onReconnect={() => {
          void run.reconnect();
        }}
        showReconnect={running && run.disconnected}
        sendBlockedReason={sendBlockReason}
        reconnectAttempt={run.reconnectAttempt}
        reconnectMaxAttempts={MAX_RECONNECT_ATTEMPTS}
        nextRetryMs={run.nextRetryMs}
        reconnectExhausted={run.reconnectExhausted}
        seedText={composerSeed.text || null}
        seedKey={composerSeed.key}
      />
    </section>
  );
}
