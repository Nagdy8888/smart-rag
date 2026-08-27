/**
 * Ask answer column: transcript, progress, composer, and prompt chips.
 */

"use client";

import { useMemo, type RefObject } from "react";
import { shouldShowCitations } from "../../lib/answer-origin";
import { citationChipHref } from "../../lib/citation-drawer";
import type { ChatViewState } from "../../lib/chat-view";
import { paidSendBlockReason, type HandshakeDecision } from "../../lib/handshake";
import {
  isGraphOnlyInspectionRoute,
  limitationCopy,
  limitationTone,
} from "../../lib/limitations";
import { MAX_RECONNECT_ATTEMPTS } from "../../lib/stream-reconnect";
import type { CitationResponse, ConversationMessage, ReadinessResponse } from "../../lib/types";
import { Button } from "../ui/button";
import { LimitationCallout } from "../ui/limitation-callout";
import { AnswerSurface } from "./answer-surface";
import { ChatComposer } from "./chat-composer";
import { FeedbackPopover } from "./feedback-popover";
import type { UseChatRunResult } from "./hooks/use-chat-run";
import { RunDetailsSheet } from "./run-details-sheet";
import type { FeedbackTag } from "../../lib/types";
import chatStyles from "./chat-transcript.module.css";

const PROMPT_CHIPS = [
  "Summarize an uploaded policy",
  "Compare two documented values",
  "Find a relationship between entities",
] as const;

export type ChatStageProps = {
  chat: ChatViewState;
  run: UseChatRunResult;
  historyMessages: ConversationMessage[];
  /** True while the selected conversation transcript is fetching. */
  messagesPending?: boolean;
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
};

/**
 * Compose the live answer column.
 *
 * @param props - Run view, transcript, and composer bindings.
 * @returns Stage section.
 */
export function ChatStage(props: ChatStageProps) {
  const {
    chat,
    run,
    historyMessages,
    messagesPending = false,
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
  } = props;
  const running = chat.terminal === null && chat.runId !== null;
  const sendBlockReason = paidSendBlockReason(
    handshake,
    readyPending ? undefined : ready,
    chat,
  );
  const visibleCitations = shouldShowCitations(chat.answerOrigin) ? [...citations] : [];
  const showEmptyPrompts =
    !messagesPending &&
    run.lastUserMessage === "" &&
    chat.answerText === "" &&
    historyMessages.length === 0;
  const bm25Limitation = chat.diagnostics.limitationCodes.includes("bm25_unavailable");
  const hrefForCitation = useMemo(
    () => (citation: CitationResponse) =>
      citationChipHref(citation.provenance.url) ?? undefined,
    [],
  );

  return (
    <section className={chatStyles.stage} aria-label="Answer">
      <div className={chatStyles.stageHeader}>
        <div className={chatStyles.row}>
          <span className={chatStyles.autoChip} data-testid="auto-label">
            Auto
          </span>
          <Button
            type="button"
            variant="ghost"
            data-action-id="ask.sources"
            onClick={onSourcesOpen}
          >
            Sources ({String(visibleCitations.length)})
          </Button>
          <RunDetailsSheet
            open={detailsOpen}
            onOpen={() => onDetailsOpen(true)}
            onClose={() => onDetailsOpen(false)}
            chat={chat}
            companyUsd={companyUsd}
          />
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
          verificationCompleted={chat.progress.verificationCompleted}
          chat={chat}
          hrefForCitation={hrefForCitation}
          onSelectCitation={onSelectCitation}
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
        {chat.terminal !== null && chat.answerText !== "" ? (
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
