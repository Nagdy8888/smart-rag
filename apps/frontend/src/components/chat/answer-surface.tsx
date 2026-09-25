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
import {
  LEGACY_RUN_SOURCES_LABEL,
  citationChipName,
  citationSourceLabel,
  citationsForParagraph,
  splitVerifiedParagraphs,
  unmappedCitations,
} from "../../lib/citation-label";
import type { RunProgressItem } from "../../lib/run-progress";
import type { ChatViewState } from "../../lib/chat-view";
import type { CitationResponse, ConversationMessage } from "../../lib/types";
import { formatRunTokenUsage } from "../../lib/format-usage";
import {
  EMPTY_DEADLINE_PARTIAL_COPY,
  isDeadlinePartialStatus,
  routeLabel,
} from "../../lib/run-details";
import { formatRelativeTime } from "../../lib/relative-time";
import { displayText } from "../../lib/safe-text";
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
  /** True when the selected transcript query failed. */
  messagesError?: boolean;
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
  /** Open Sources for a historical assistant's owned run. */
  onOpenTurnSources?: (runId: string) => void;
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
 * @param status - SSE `partial.reason` or error code stored on the view.
 * @returns One sentence, or null.
 */
export function answerTerminalNote(
  terminal: string | null,
  answer: string,
  status: string | null = null,
): string | null {
  if (terminal === "partial" && isDeadlinePartialStatus(status) && answer.trim() === "") {
    return EMPTY_DEADLINE_PARTIAL_COPY;
  }
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
 * Return whether persisted transcript text is the same live Ask string.
 *
 * `GET /conversations/{id}/messages` HTML-escapes content. SSE `answerText`
 * and the composer question are already decoded. Compare decoded strings so
 * apostrophes and quotes do not keep a second copy of the same turn.
 *
 * @param persisted - Escaped history `content`, or undefined when missing.
 * @param live - Decoded live question or verified answer.
 * @returns True when both sides display the same non-empty text.
 */
export function transcriptTextMatches(
  persisted: string | undefined,
  live: string,
): boolean {
  if (persisted === undefined || live === "") {
    return false;
  }
  return displayText(persisted) === displayText(live);
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
  hrefForCitation,
  onSelectCitation,
  testId,
  className,
}: {
  citations: CitationResponse[];
  hrefForCitation: (citation: CitationResponse) => string | undefined;
  onSelectCitation: (
    citation: CitationResponse,
    trigger: HTMLButtonElement,
  ) => void;
  testId?: string;
  className?: string;
}) {
  if (citations.length === 0) {
    return null;
  }
  return (
    <ul
      className={className ? `${styles.citationRow} ${className}` : styles.citationRow}
      data-testid={testId}
    >
      {citations.map((citation) => (
        <li key={citation.citation_id}>
          <CitationChip
            index={citation.citation_index}
            label={citationSourceLabel(citation)}
            name={citationChipName(citation)}
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
 * Render chips that belong to one verified paragraph.
 *
 * @param props - Mapped citations and chip handlers.
 * @returns Citation list, or null.
 */
export function ParagraphCitations({
  citations,
  hrefForCitation,
  onSelectCitation,
}: {
  citations: CitationResponse[];
  hrefForCitation: (citation: CitationResponse) => string | undefined;
  onSelectCitation: (
    citation: CitationResponse,
    trigger: HTMLButtonElement,
  ) => void;
}) {
  return (
    <CitationRow
      citations={citations}
      hrefForCitation={hrefForCitation}
      onSelectCitation={onSelectCitation}
      testId="paragraph-citations"
    />
  );
}

/**
 * Return the visible slice of one paragraph during paced reveal.
 *
 * @param paragraphs - Full `\n\n`-split answer.
 * @param paragraphIndex - 0-based paragraph.
 * @param visibleText - Currently presented prefix of the full answer.
 * @returns Visible text and whether the paragraph is complete.
 */
export function visibleParagraphSlice(
  paragraphs: readonly string[],
  paragraphIndex: number,
  visibleText: string,
): { text: string; complete: boolean } {
  const start = paragraphs.slice(0, paragraphIndex).join("\n\n");
  const startLen = start.length === 0 ? 0 : start.length + 2;
  if (visibleText.length <= startLen) {
    return { text: "", complete: false };
  }
  const paragraph = paragraphs[paragraphIndex] ?? "";
  const available = visibleText.slice(startLen);
  if (available.length >= paragraph.length) {
    return { text: paragraph, complete: true };
  }
  return { text: available, complete: false };
}

/**
 * Render verified paragraphs with inline chips and a legacy footer.
 *
 * @param props - Full answer, visible prefix, citations, and chip handlers.
 * @returns Paragraph blocks. Chips wait until their paragraph is fully visible.
 */
function AnswerParagraphs({
  answerText,
  visibleText,
  citations,
  answerOrigin,
  hrefForCitation,
  onSelectCitation,
}: {
  answerText: string;
  visibleText: string;
  citations: readonly CitationResponse[];
  answerOrigin: string | null;
  hrefForCitation: (citation: CitationResponse) => string | undefined;
  onSelectCitation: (
    citation: CitationResponse,
    trigger: HTMLButtonElement,
  ) => void;
}) {
  const paragraphs = splitVerifiedParagraphs(answerText);
  const showChips = shouldShowCitations(answerOrigin);
  const visibleCitations = showChips ? [...citations] : [];
  const leftover = unmappedCitations(visibleCitations, paragraphs.length);

  return (
    <div
      className={styles.answerBody}
      data-testid={
        showChips && visibleCitations.length > 0 ? "answer-citations" : undefined
      }
    >
      {paragraphs.map((_, index) => {
        const slice = visibleParagraphSlice(paragraphs, index, visibleText);
        if (slice.text === "") {
          return null;
        }
        const mapped = slice.complete
          ? citationsForParagraph(visibleCitations, index)
          : [];
        return (
          <div
            className={styles.paragraphBlock}
            data-paragraph-index={String(index)}
            key={`p-${String(index)}`}
          >
            <p className={styles.answerProse} dir="auto">
              <UserText value={slice.text} />
            </p>
            <ParagraphCitations
              citations={mapped}
              hrefForCitation={hrefForCitation}
              onSelectCitation={onSelectCitation}
            />
          </div>
        );
      })}
      {showChips && leftover.length > 0 && visibleText === answerText ? (
        <div className={styles.legacySources}>
          <p className={styles.legacySourcesLabel}>{LEGACY_RUN_SOURCES_LABEL}</p>
          <CitationRow
            citations={leftover}
            hrefForCitation={hrefForCitation}
            onSelectCitation={onSelectCitation}
            testId="legacy-citations"
          />
        </div>
      ) : null}
    </div>
  );
}

/**
 * Render the question block and editorial answer.
 *
 * @param props - History, live run, optional origin, and route.
 * @returns Answer column. Origin is never inferred from the route pill.
 * @remarks
 * Render-isolation contract: this column is the only subtree that should
 * re-render on SSE `token_delta` batches. After transcript refetch, live
 * question/answer chrome is omitted when decoded persisted content already
 * matches so apostrophes cannot keep a second copy of the same turn.
 */
export const AnswerSurface = memo(function AnswerSurface({
  messages = [],
  messagesPending = false,
  messagesError = false,
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
  onOpenTurnSources,
}: AnswerSurfaceProps) {
  const note = answerTerminalNote(terminal, answer, chat?.status ?? null);
  const originLabel = answerOriginLabel(answerOrigin);
  const routeName = routeLabel(effectiveRoute);
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
  const showLiveUser =
    question !== "" && !transcriptTextMatches(lastHistUser?.content, question);
  const showProgress =
    progressItems.length > 0 ||
    statusLine !== null ||
    (chat !== null && chat.terminal === null && chat.runId !== null);
  const showLiveAssistant =
    (showProgress || answer !== "") &&
    !transcriptTextMatches(lastHistAssistant?.content, answer);
  const empty =
    !messagesPending &&
    !messagesError &&
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
      {messagesError && !messagesPending && messages.length === 0 ? (
        <LimitationCallout tone="warning">
          Couldn&apos;t load this conversation.
        </LimitationCallout>
      ) : null}
      {empty ? (
        <EmptyState
          title="Ask about your documents"
          body="Answers from company documents cite the passages they use. General questions are answered without citations."
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
              <AnswerParagraphs
                answerText={item.content}
                visibleText={item.content}
                citations={[]}
                answerOrigin={null}
                hrefForCitation={hrefForCitation}
                onSelectCitation={onSelectCitation}
              />
            </LiveRegion>
            <p className={styles.messageMeta}>
              {formatRelativeTime(item.created_at)}
              {(item.citation_count ?? 0) > 0 && item.run_id ? (
                <>
                  {" · "}
                  <Button
                    type="button"
                    variant="ghost"
                    size="compact"
                    data-action-id="ask.turn_sources"
                    onClick={() => {
                      if (item.run_id) {
                        onOpenTurnSources?.(item.run_id);
                      }
                    }}
                  >
                    {`Sources (${String(item.citation_count)})`}
                  </Button>
                </>
              ) : null}
            </p>
          </div>
        ),
      )}
      {showLiveUser ? (
        <p className={`${styles.userBubble} ${styles.liveTurn}`} dir="auto">
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
        <div className={styles.liveTurn}>
          {originLabel !== null ? (
            <p className={styles.answerHeader}>
              <Badge label={originLabel} data-testid="answer-origin" />
              {routeName ? (
                <span data-testid="answer-route">
                  <StatusPill status={routeName} />
                </span>
              ) : null}
            </p>
          ) : routeName ? (
            <p className={styles.answerHeader}>
              <span data-testid="answer-route">
                <StatusPill status={routeName} />
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
            >
              {shouldShowCitations(answerOrigin) ? (
                <AnswerParagraphs
                  answerText={answer}
                  visibleText={visibleAnswer ?? answer}
                  citations={citations}
                  answerOrigin={answerOrigin}
                  hrefForCitation={hrefForCitation}
                  onSelectCitation={onSelectCitation}
                />
              ) : null}
            </VerifiedAnswerReveal>
          ) : null}
          {showClarification ? (
            <LimitationCallout tone="warning">{MIXED_SCOPE_CLARIFICATION}</LimitationCallout>
          ) : null}
          <p className={styles.messageMeta}>
            {liveCreatedAt ? formatRelativeTime(liveCreatedAt) : null}
            {routeName ? ` · ${routeName}` : null}
            {usageLabel !== null ? (
              <>
                {liveCreatedAt || routeName ? " · " : null}
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
