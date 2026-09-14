/**
 * Owner/admin Save to quiz popover. Separate from Give feedback.
 */

"use client";

import {
  QUIZ_MAX_GOLD_CHUNKS,
  QUIZ_RETENTION_DISCLOSURE,
  QUIZ_SCORE_NOT_RECALL_LABEL,
} from "../../lib/eval-workspace";
import { citationSourceLabel } from "../../lib/citation-label";
import type { CitationResponse, PdfEvalCaseSummary, PdfEvalQueryClass } from "../../lib/types";
import { PDF_EVAL_QUERY_CLASSES } from "../../lib/types";
import { Button } from "../ui/button";
import { Popover } from "../ui/popover";
import { Select } from "../ui/select";
import { Textarea } from "../ui/textarea";
import { UserText } from "../ui/user-text";
import styles from "./chat-transcript.module.css";

const QUERY_CLASS_LABELS: Record<PdfEvalQueryClass, string> = {
  factual_definition: "Factual definition",
  exact_acronym: "Exact acronym",
  semantic_paraphrase: "Semantic paraphrase",
  multi_part: "Multi-part",
  section_scoped: "Section scoped",
};

export type SaveToQuizPopoverProps = {
  /** Question from the current run. Display only; never posted. */
  question: string;
  /** ACL-rechecked citations for optional gold suggestions. */
  citations: readonly CitationResponse[];
  queryClass: PdfEvalQueryClass;
  onQueryClass: (value: PdfEvalQueryClass) => void;
  expectedAnswer: string;
  onExpectedAnswer: (value: string) => void;
  selectedChunkIds: readonly string[];
  goldBlocked: boolean;
  onToggleChunk: (chunkId: string) => void;
  savePending: boolean;
  saveError: string | null;
  saveNotice: string | null;
  onSave: () => void;
  cases: readonly PdfEvalCaseSummary[];
  casesPending: boolean;
  casesError: boolean;
  nextCaseId: string | null;
  loadMorePending: boolean;
  onLoadMore: () => void;
  selectedCaseId: string | null;
  onSelectCase: (caseId: string) => void;
  selectedQuestion: string;
  detailPending: boolean;
  onAskQuestion: () => void;
  scoreAllowed: boolean;
  scoreReason: string;
  scorePending: boolean;
  scoreNotice: string | null;
  onScore: () => void;
};

/**
 * Render Save to quiz beside ordinary feedback.
 *
 * @param props - Controlled quiz fields from `useQuizCapture`.
 * @returns Popover. Create posts the run id; question text is omitted.
 */
export function SaveToQuizPopover(props: SaveToQuizPopoverProps) {
  const goldCandidates = props.citations.filter(
    (item) => typeof item.chunk_id === "string" && item.chunk_id !== "",
  );
  const atCap = props.selectedChunkIds.length >= QUIZ_MAX_GOLD_CHUNKS;
  return (
    <Popover label="Save to quiz" trigger="Save to quiz" actionId="ask.quiz.save">
      <div className={styles.feedbackForm}>
        <p className={styles.muted}>{QUIZ_RETENTION_DISCLOSURE}</p>
        <p className={styles.muted}>
          Question from this run (saved from the run, not this text box):
        </p>
        <p>
          <UserText value={props.question} />
        </p>
        <Select
          label="Query class"
          value={props.queryClass}
          options={PDF_EVAL_QUERY_CLASSES.map((item) => ({
            value: item,
            label: QUERY_CLASS_LABELS[item],
          }))}
          onChange={(event) =>
            props.onQueryClass(event.target.value as PdfEvalQueryClass)
          }
        />
        <Textarea
          label="Expected answer (optional)"
          value={props.expectedAnswer}
          onChange={(event) => props.onExpectedAnswer(event.target.value)}
        />
        <fieldset className={styles.quizGoldFieldset}>
          <legend>Gold citations (0–3)</legend>
          {goldCandidates.length === 0 ? (
            <p className={styles.muted}>No citations on this run. Zero-gold drafts are allowed.</p>
          ) : (
            goldCandidates.map((citation) => {
              const chunkId = citation.chunk_id as string;
              const checked = props.selectedChunkIds.includes(chunkId);
              const blocked = atCap && !checked;
              return (
                <label key={citation.citation_id} className={styles.quizGoldLabel}>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={blocked}
                    aria-disabled={blocked ? true : undefined}
                    onChange={() => props.onToggleChunk(chunkId)}
                  />{" "}
                  <UserText value={citationSourceLabel(citation)} />
                </label>
              );
            })
          )}
          {props.goldBlocked || atCap ? (
            <p className={styles.muted} role="status">
              At most three gold citations.
            </p>
          ) : null}
        </fieldset>
        <Button
          type="button"
          data-action-id="ask.quiz.submit"
          pending={props.savePending}
          pendingLabel="Saving…"
          onClick={props.onSave}
        >
          Save draft
        </Button>
        {props.saveNotice ? (
          <p className={styles.muted} role="status">
            {props.saveNotice}
          </p>
        ) : null}
        {props.saveError ? (
          <p className={styles.muted} role="status">
            {props.saveError}
          </p>
        ) : null}
        <h3 className={styles.quizHeading}>Saved cases</h3>
        {props.casesPending ? <p className={styles.muted}>Loading saved cases…</p> : null}
        {props.casesError ? (
          <p className={styles.muted} role="status">
            Saved cases could not load. Try again.
          </p>
        ) : null}
        {!props.casesPending && props.cases.length === 0 ? (
          <p className={styles.muted}>No saved cases yet.</p>
        ) : (
          <ul className={styles.quizCaseList} aria-label="Saved quiz cases">
            {props.cases.map((item) => {
              const current = item.case_id === props.selectedCaseId;
              return (
                <li key={item.case_id}>
                  <button
                    type="button"
                    className={
                      current ? styles.quizCaseButtonCurrent : styles.quizCaseButton
                    }
                    aria-current={current ? "true" : undefined}
                    onClick={() => props.onSelectCase(item.case_id)}
                  >
                    <UserText value={item.query_class} />
                    <span className={styles.muted}>
                      {" "}
                      {item.review_status} · {item.split}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {props.nextCaseId ? (
          <Button
            type="button"
            data-action-id="ask.quiz.load_more"
            pending={props.loadMorePending}
            pendingLabel="Loading…"
            onClick={props.onLoadMore}
          >
            Load more
          </Button>
        ) : null}
        {props.detailPending ? <p className={styles.muted}>Loading case…</p> : null}
        {props.selectedCaseId && props.selectedQuestion ? (
          <p>
            <UserText value={props.selectedQuestion} />
          </p>
        ) : null}
        <div className={styles.row}>
          <Button
            type="button"
            data-action-id="ask.quiz.ask_question"
            disabled={props.selectedQuestion === ""}
            disabledReason={
              props.selectedQuestion === ""
                ? "Select a saved case first."
                : undefined
            }
            onClick={props.onAskQuestion}
          >
            Ask this question
          </Button>
          <Button
            type="button"
            data-action-id="ask.quiz.score"
            disabled={!props.scoreAllowed}
            disabledReason={
              props.scoreAllowed
                ? undefined
                : props.scoreReason ||
                  `Score this answer only for a pre-existing approved case. ${QUIZ_SCORE_NOT_RECALL_LABEL}`
            }
            pending={props.scorePending}
            pendingLabel="Scoring…"
            onClick={props.onScore}
          >
            Score this answer ({QUIZ_SCORE_NOT_RECALL_LABEL})
          </Button>
        </div>
        {props.scoreNotice ? (
          <p className={styles.muted} role="status">
            {props.scoreNotice}
          </p>
        ) : null}
      </div>
    </Popover>
  );
}
