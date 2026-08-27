/**
 * Transcript and live answer surface.
 */

"use client";

import { memo } from "react";
import {
  MIXED_SCOPE_CLARIFICATION,
  answerOriginLabel,
  shouldShowCitations,
} from "../../lib/answer-origin";
import type { RunProgressItem } from "../../lib/run-progress";
import type { ChatViewState } from "../../lib/chat-view";
import type { CitationResponse, ConversationMessage } from "../../lib/types";
import { formatRunTokenUsage } from "../../lib/format-usage";
import { formatRelativeTime } from "../../lib/relative-time";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { CitationChip } from "../ui/citation-chip";
import { EmptyState } from "../ui/empty-state";
import { LimitationCallout } from "../ui/limitation-callout";
import { LiveRegion } from "../ui/live-region";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import { RunProgressTimeline } from "./run-progress-timeline";
import { VerifiedAnswerReveal } from "./verified-answer-reveal";
import styles from "./chat-transcript.module.css";

export type AnswerSurfaceProps = {
  /** Persisted messages in ascending order. */
  messages?: ConversationMessage[];
  /** True while the selected transcript query is in flight. */
  messagesPending?: boolean;
  /** True when an older page is available. */
  hasEarlier?: boolean;
  /** Load the previous transcript page. */
  onLoadEarlier?: () => void;
  /** True while an older page is fetching. */
  loadingEarlier?: boolean;
  /** In-flight question not yet in `messages`. */
  question: string;
  /** Assistant tokens so far. */
  answer: string;
  /** Citations for the current run. */
  citations: CitationResponse[];
  /** Build a chip href from provenance. */
  hrefForCitation: (citation: CitationResponse) => string | undefined;
  /** Open the sources drawer from a chip. */
  onSelectCitation: (
    citation: CitationResponse,
    trigger: HTMLButtonElement,
  ) => void;
  /** Terminal status for the current run. */
  terminal: string | null;
  /** Additive answer origin, or null for older servers. */
  answerOrigin?: string | null;
  /** Effective route family. Never used to infer origin. */
  effectiveRoute?: string | null;
  /** One-line run status while active. Prefer `progressItems`. */
  statusLine?: string | null;
  /** Reducer progress rows. Empty when no node has started. */
  progressItems?: readonly RunProgressItem[];
  /** True after verify_answer completed. */
  verificationCompleted?: boolean;
  /** Live chat view for truthful summary copy. */
  chat?: ChatViewState | null;
  /** True while verified text is still being presented. */
  revealing?: boolean;
  /** Visible verified prefix. Defaults to `answer`. */
  visibleAnswer?: string;
  /** Conversation + run presentation key. */
  presentationKey?: string;
  /** Complete the live reveal immediately. */
  onShowFullAnswer?: () => void;
  /** Safe copy when Load earlier failed. */
  loadEarlierError?: string | null;
  /** Relative time for the live assistant meta row. */
  liveCreatedAt?: string | null;
  /** Provider prompt tokens for the current run. */
  promptTokens?: number;
  /** Provider completion tokens for the current run. */
  completionTokens?: number;
};

/**
 * Return the answer-column terminal note, or null when chrome owns the alert.
 *
 * @param terminal - Catalog terminal or null.
 * @param answer - Tokens already shown.
 * @returns One sentence, or null.
 */
export function answerTerminalNote(
  terminal: string | null,
  answer: string,
): string | null {
  if (terminal === "partial") {
    return "Partial answer. Verified tokens are kept.";
  }
  if (terminal === "cancelled") {
    return "Cancelled. Received tokens are kept.";
  }
  if (terminal === "deadline") {
    return "Deadline reached. This run is not complete.";
  }
  if (terminal === "error") {
    return answer.trim() === ""
      ? null
      : "The run ended in an error. Received tokens are kept.";
  }
  if (terminal) {
    return "Answer ready.";
  }
  return null;
}

/**
 * Render citation chips for a company or legacy-null origin.
 *
 * @param citations - Authorized citations.
 * @param answerOrigin - Additive origin.
 * @param hrefForCitation - Chip href builder.
 * @param onSelectCitation - Open the citation drawer.
 * @returns List, or null.
 */
function CitationRow({
  citations,
  answerOrigin,
  hrefForCitation,
  onSelectCitation,
}: {
  citations: CitationResponse[];
  answerOrigin: string | null;
  hrefForCitation: (citation: CitationResponse) => string | undefined;
  onSelectCitation: (
    citation: CitationResponse,
    trigger: HTMLButtonElement,
  ) => void;
}) {
  const visible = shouldShowCitations(answerOrigin) ? citations : [];
  if (visible.length === 0) {
    return null;
  }
  return (
    <ul className={styles.citationRow} data-testid="answer-citations">
      {visible.map((citation) => (
        <li key={citation.citation_id}>
          <CitationChip
            index={citation.citation_index}
            citationId={citation.citation_id}
            unavailable={citation.source_unavailable}
            href={hrefForCitation(citation)}
            onSelect={(trigger) => {
              onSelectCitation(citation, trigger);
            }}
          />
        </li>
      ))}
    </ul>
  );
}

/**
 * Render the question block and editorial answer.
 *
 * @param props - History, live run, optional origin, and route.
 * @returns Answer column. Origin is never inferred from the route pill.
 * @remarks
 * Render-isolation contract: this column is the only subtree that should
 * re-render on SSE `token_delta` batches.
 */
export const AnswerSurface = memo(function AnswerSurface({
  messages = [],
  messagesPending = false,
  hasEarlier = false,
  onLoadEarlier,
  loadingEarlier = false,
  question,
  answer,
  citations,
  hrefForCitation,
  onSelectCitation,
  terminal,
  answerOrigin = null,
  effectiveRoute = null,
  statusLine = null,
  progressItems = [],
  verificationCompleted = false,
  chat = null,
  revealing = false,
  visibleAnswer,
  presentationKey = "live",
  onShowFullAnswer,
  loadEarlierError = null,
  liveCreatedAt = null,
  promptTokens = 0,
  completionTokens = 0,
}: AnswerSurfaceProps) {
  const note = answerTerminalNote(terminal, answer);
  const originLabel = answerOriginLabel(answerOrigin);
  const usageLabel = formatRunTokenUsage(promptTokens, completionTokens);
  const showClarification = answerOrigin === "ambiguous";
  const terminalClass =
    terminal === "partial"
      ? styles.terminalPartial
      : terminal === "cancelled"
        ? styles.terminalCancelled
        : terminal === "error"
          ? styles.terminalError
          : terminal === "deadline"
            ? styles.terminalDeadline
            : styles.terminalNote;
  const lastHistUser = [...messages].reverse().find((item) => item.role === "user");
  const lastHistAssistant = [...messages]
    .reverse()
    .find((item) => item.role === "assistant");
  const showLiveUser = question !== "" && lastHistUser?.content !== question;
  const showProgress =
    progressItems.length > 0 ||
    statusLine !== null ||
    (chat !== null && chat.terminal === null && chat.runId !== null);
  const showLiveAssistant =
    (showProgress || answer !== "") &&
    lastHistAssistant?.content !== answer;
  const empty =
    !messagesPending &&
    messages.length === 0 &&
    !showLiveUser &&
    !showLiveAssistant &&
    question === "" &&
    answer === "";

  return (
    <div className={styles.answer}>
      {hasEarlier && onLoadEarlier ? (
        <Button
          type="button"
          variant="ghost"
          pending={loadingEarlier}
          pendingLabel="Loading…"
          onClick={onLoadEarlier}
        >
          Load earlier messages
        </Button>
      ) : null}
      {loadEarlierError ? (
        <LimitationCallout tone="warning">
          {loadEarlierError}
          {onLoadEarlier ? (
            <Button type="button" variant="ghost" onClick={onLoadEarlier}>
              Retry
            </Button>
          ) : null}
        </LimitationCallout>
      ) : null}
      {messagesPending && messages.length === 0 ? (
        <p className={styles.muted}>Loading conversation…</p>
      ) : null}
      {empty ? (
        <EmptyState
          title="Ask your company knowledge"
          body="Answers come from your authorized documents, with citations you can inspect."
        />
      ) : null}
      {messages.map((item) =>
        item.role === "user" ? (
          <p key={item.message_id} className={styles.userBubble} dir="auto">
            <UserText value={item.content} />
          </p>
        ) : (
          <div key={item.message_id} className={styles.assistantBlock}>
            <LiveRegion aria-label="Answer" politeness="polite">
              <p className={styles.answerProse} dir="auto">
                <UserText value={item.content} />
              </p>
            </LiveRegion>
            <p className={styles.messageMeta}>
              {formatRelativeTime(item.created_at)}
            </p>
          </div>
        ),
      )}
      {showLiveUser ? (
        <p className={styles.userBubble} dir="auto">
          <UserText value={question} />
        </p>
      ) : null}
      {showProgress ? (
        <RunProgressTimeline
          items={progressItems}
          terminal={terminal}
          verificationCompleted={verificationCompleted}
          answerAvailable={answer.trim() !== ""}
          collapsed={verificationCompleted && answer.trim() !== "" && !revealing}
          chat={chat}
          revealing={revealing}
        />
      ) : null}
      {showLiveAssistant ? (
        <div>
          {originLabel !== null ? (
            <p className={styles.answerHeader}>
              <Badge label={originLabel} data-testid="answer-origin" />
              {effectiveRoute ? (
                <span data-testid="answer-route">
                  <StatusPill status={effectiveRoute} />
                </span>
              ) : null}
            </p>
          ) : effectiveRoute ? (
            <p className={styles.answerHeader}>
              <span data-testid="answer-route">
                <StatusPill status={effectiveRoute} />
              </span>
            </p>
          ) : null}
          {answer ? (
            <VerifiedAnswerReveal
              presentationKey={presentationKey}
              visibleText={visibleAnswer ?? answer}
              isRevealing={revealing}
              authoritativeReady={answer.trim() !== ""}
              onShowFull={onShowFullAnswer ?? (() => undefined)}
            />
          ) : null}
          <CitationRow
            citations={citations}
            answerOrigin={answerOrigin}
            hrefForCitation={hrefForCitation}
            onSelectCitation={onSelectCitation}
          />
          {showClarification ? (
            <LimitationCallout tone="warning">{MIXED_SCOPE_CLARIFICATION}</LimitationCallout>
          ) : null}
          <p className={styles.messageMeta}>
            {liveCreatedAt ? formatRelativeTime(liveCreatedAt) : null}
            {effectiveRoute ? ` · ${effectiveRoute}` : null}
            {usageLabel !== null ? (
              <>
                {liveCreatedAt || effectiveRoute ? " · " : null}
                <span data-testid="answer-token-usage">{usageLabel}</span>
              </>
            ) : null}
          </p>
          {note !== null ? (
            <p className={`${styles.terminalNote} ${terminalClass}`}>{note}</p>
          ) : null}
        </div>
      ) : (
        <LiveRegion aria-label="Answer" politeness="polite">
          {""}
        </LiveRegion>
      )}
    </div>
  );
});
