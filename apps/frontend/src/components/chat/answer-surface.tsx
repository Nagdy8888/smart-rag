/**
 * Editorial answer surface. One in-memory question and answer.
 */

"use client";

import type { CitationResponse } from "../../lib/types";
import { CitationChip } from "../ui/citation-chip";
import { EmptyState } from "../ui/empty-state";
import { Icon } from "../ui/icon";
import { LiveRegion } from "../ui/live-region";
import { UserText } from "../ui/user-text";
import styles from "./chat.module.css";

export type AnswerSurfaceProps = {
  /** Last submitted question, or empty. */
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
};

/**
 * Render the question block and editorial answer.
 *
 * @param props - Controlled transcript data.
 * @returns Answer column. Does not fetch history.
 */
export function AnswerSurface({
  question,
  answer,
  citations,
  hrefForCitation,
  onSelectCitation,
  terminal,
}: AnswerSurfaceProps) {
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
  return (
    <div className={styles.answer}>
      {question ? (
        <p className={styles.queryBlock} dir="auto">
          <UserText value={question} />
        </p>
      ) : (
        <EmptyState title="Ask your company knowledge.">
          <Icon name="spark" />
          Answers come from authorized documents and include available evidence.
        </EmptyState>
      )}
      {answer ? (
        <div>
          <p className={styles.answerHeader}>
            <Icon name="spark" />
            Answer
          </p>
          <LiveRegion aria-label="Answer" politeness="polite">
            <p className={styles.answerProse} dir="auto">
              <UserText value={answer} />
            </p>
          </LiveRegion>
        </div>
      ) : (
        <LiveRegion aria-label="Answer" politeness="polite">{""}</LiveRegion>
      )}
      {citations.length > 0 ? (
        <ul className={styles.citationRow}>
          {citations.map((citation) => (
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
      ) : null}
      {terminal ? (
        <p className={`${styles.terminalNote} ${terminalClass}`}>
          {terminal === "partial"
            ? "Partial answer. Verified tokens are kept."
            : terminal === "cancelled"
              ? "Cancelled. Received tokens are kept."
              : terminal === "deadline"
                ? "Deadline reached. This run is not complete."
                : terminal === "error"
                  ? "The run ended in an error. Received tokens are kept."
                  : "Answer ready."}
        </p>
      ) : null}
    </div>
  );
}
