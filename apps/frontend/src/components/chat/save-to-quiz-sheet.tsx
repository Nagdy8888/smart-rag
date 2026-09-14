/**
 * Owner/admin Save to quiz sheet. Separate from Give feedback.
 */

"use client";

import {
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import {
  QUIZ_MAX_GOLD_CHUNKS,
  QUIZ_RETENTION_DISCLOSURE,
  QUIZ_SCORE_NOT_RECALL_LABEL,
} from "../../lib/eval-workspace";
import { citationSourceLabel } from "../../lib/citation-label";
import type { CitationResponse, PdfEvalCaseSummary, PdfEvalQueryClass } from "../../lib/types";
import { PDF_EVAL_QUERY_CLASSES } from "../../lib/types";
import {
  queryClassLabel,
  reviewStatusLabel,
  reviewStatusTone,
  sourceCountLabel,
} from "../evaluation/evaluation-presenters";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/empty-state";
import { Icon } from "../ui/icon";
import { Select } from "../ui/select";
import { Sheet } from "../ui/sheet";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import { Textarea } from "../ui/textarea";
import { UserText } from "../ui/user-text";
import styles from "./save-to-quiz-sheet.module.css";

const QUERY_CLASS_OPTIONS: Record<PdfEvalQueryClass, string> = {
  factual_definition: "Direct fact or definition",
  exact_acronym: "Exact term or acronym",
  semantic_paraphrase: "Paraphrased meaning",
  multi_part: "Multi-part question",
  section_scoped: "Specific section",
};

const QUIZ_VIEWS = ["new", "saved"] as const;

type QuizSheetView = (typeof QUIZ_VIEWS)[number];

export type SaveToQuizSheetProps = {
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
  onRetryCases: () => void;
  nextCaseId: string | null;
  loadMorePending: boolean;
  loadMoreError: boolean;
  onLoadMore: () => void;
  selectedCaseId: string | null;
  onSelectCase: (caseId: string) => void;
  selectedQuestion: string;
  detailPending: boolean;
  detailError: boolean;
  onRetryDetail: () => void;
  onAskQuestion: () => void;
  scoreAllowed: boolean;
  scoreReason: string;
  scorePending: boolean;
  scoreNotice: string | null;
  scoreError: string | null;
  onScore: () => void;
};

/**
 * Render Save to quiz beside ordinary feedback.
 *
 * @param props - Controlled quiz fields from `useQuizCapture`.
 * @returns Footer trigger plus modal sheet. Create posts the run id;
 *   question text is omitted. Ask this question fills the composer only.
 * @remarks
 * Opening always lands on New case. Form values live in the capture hook so
 * close/reopen does not erase them. Hidden chrome is not authorization.
 */
export function SaveToQuizSheet(props: SaveToQuizSheetProps) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<QuizSheetView>("new");
  const triggerRef = useRef<HTMLButtonElement>(null);
  const tabRefs = useRef<Partial<Record<QuizSheetView, HTMLButtonElement | null>>>(
    {},
  );
  const id = useId();
  const newTabId = `${id}-tab-new`;
  const savedTabId = `${id}-tab-saved`;
  const newPanelId = `${id}-panel-new`;
  const savedPanelId = `${id}-panel-saved`;
  const expectedId = `${id}-expected`;
  const expectedHelperId = `${id}-expected-helper`;

  /**
   * Open on New case so reuse work does not hide the current-run form.
   */
  function openSheet(): void {
    setView("new");
    setOpen(true);
  }

  /**
   * Close the sheet and restore focus through Sheet's trap.
   */
  function closeSheet(): void {
    setOpen(false);
  }

  /**
   * Fill the composer with the saved question only, then close so the field
   * is visible. Expected-answer text is not in this callback.
   */
  function askSelectedQuestion(): void {
    props.onAskQuestion();
    closeSheet();
  }

  /**
   * Move among the two task tabs with arrows, wrapping at the ends.
   *
   * @param event - Keyboard event from the focused tab.
   * @param index - Focused tab index.
   */
  function onTabKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ): void {
    const last = QUIZ_VIEWS.length - 1;
    let next = index;
    if (event.key === "ArrowRight") {
      next = index === last ? 0 : index + 1;
    } else if (event.key === "ArrowLeft") {
      next = index === 0 ? last : index - 1;
    } else if (event.key === "Home") {
      next = 0;
    } else if (event.key === "End") {
      next = last;
    } else {
      return;
    }
    event.preventDefault();
    const nextView = QUIZ_VIEWS[next];
    if (nextView) {
      setView(nextView);
      tabRefs.current[nextView]?.focus();
    }
  }

  return (
    <>
      <Button
        ref={triggerRef}
        type="button"
        variant="secondary"
        data-action-id="ask.quiz.save"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={openSheet}
      >
        <Icon name="plus" />
        Save to quiz
      </Button>
      {open ? (
        <Sheet
          title="Save to quiz"
          onClose={closeSheet}
          returnFocusRef={triggerRef}
          panelClassName={styles.sheet}
        >
          <div className={styles.layout}>
            <div
              role="tablist"
              aria-label="Quiz case tasks"
              className={styles.tabList}
            >
              <button
                type="button"
                role="tab"
                id={newTabId}
                aria-selected={view === "new"}
                aria-controls={newPanelId}
                tabIndex={view === "new" ? 0 : -1}
                className={view === "new" ? styles.tabCurrent : styles.tab}
                ref={(node) => {
                  tabRefs.current.new = node;
                }}
                onClick={() => setView("new")}
                onKeyDown={(event) => onTabKeyDown(event, 0)}
              >
                New case
              </button>
              <button
                type="button"
                role="tab"
                id={savedTabId}
                aria-selected={view === "saved"}
                aria-controls={savedPanelId}
                tabIndex={view === "saved" ? 0 : -1}
                className={view === "saved" ? styles.tabCurrent : styles.tab}
                ref={(node) => {
                  tabRefs.current.saved = node;
                }}
                onClick={() => setView("saved")}
                onKeyDown={(event) => onTabKeyDown(event, 1)}
              >
                Saved cases
              </button>
            </div>
            {view === "new" ? (
              <div
                role="tabpanel"
                id={newPanelId}
                aria-labelledby={newTabId}
                className={styles.panel}
              >
                <NewCasePanel
                  sheet={props}
                  expectedId={expectedId}
                  expectedHelperId={expectedHelperId}
                  onViewSaved={() => setView("saved")}
                />
              </div>
            ) : (
              <div
                role="tabpanel"
                id={savedPanelId}
                aria-labelledby={savedTabId}
                className={styles.panel}
              >
                <SavedCasesPanel
                  sheet={props}
                  onAsk={askSelectedQuestion}
                  onCreate={() => setView("new")}
                />
              </div>
            )}
          </div>
        </Sheet>
      ) : null}
    </>
  );
}

/**
 * Create-tab fields, source picker, and sticky save footer.
 *
 * @param sheet - Controlled create fields from `useQuizCapture`.
 * @param expectedId - Textarea id for the helper description.
 * @param expectedHelperId - Helper copy id associated via `aria-describedby`.
 * @param onViewSaved - Switch to the saved tab after a successful save.
 * @returns New-case panel. Save stays open so the operator can confirm status.
 */
function NewCasePanel({
  sheet,
  expectedId,
  expectedHelperId,
  onViewSaved,
}: {
  sheet: SaveToQuizSheetProps;
  expectedId: string;
  expectedHelperId: string;
  onViewSaved: () => void;
}) {
  const goldCandidates = sheet.citations.filter(
    (item) => typeof item.chunk_id === "string" && item.chunk_id !== "",
  );
  const selectedCount = sheet.selectedChunkIds.length;
  const atCap = sheet.goldBlocked || selectedCount >= QUIZ_MAX_GOLD_CHUNKS;
  return (
    <>
      <p className={styles.lead}>
        Create a reusable evaluation case from this completed question.
      </p>
      <section className={styles.section}>
        <h3 className={styles.sectionLabel}>Question from this run</h3>
        <div className={styles.questionCard}>
          <p className={styles.questionText}>
            <UserText value={sheet.question} />
          </p>
        </div>
        <p className={styles.helper}>
          The server saves the question from the run; this preview is not
          submitted.
        </p>
      </section>
      <Select
        label="Question type"
        fullWidth
        value={sheet.queryClass}
        description="Choose the pattern this case is meant to test."
        options={PDF_EVAL_QUERY_CLASSES.map((item) => ({
          value: item,
          label: QUERY_CLASS_OPTIONS[item],
        }))}
        onChange={(event) =>
          sheet.onQueryClass(event.target.value as PdfEvalQueryClass)
        }
      />
      <div className={styles.section}>
        <Textarea
          id={expectedId}
          label="Expected answer (optional)"
          fullWidth
          rows={4}
          placeholder="Write the answer a reviewer should expect…"
          value={sheet.expectedAnswer}
          aria-describedby={expectedHelperId}
          onChange={(event) => sheet.onExpectedAnswer(event.target.value)}
        />
        <p id={expectedHelperId} className={styles.helper}>
          For reviewers only. It is never sent when this question is asked again.
        </p>
      </div>
      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>
          <span>Suggested sources</span>
          <Badge label={`${String(selectedCount)} of 3 selected`} />
        </legend>
        <p className={styles.helper}>
          Choose up to 3 citations from this answer. You can save without
          selecting one.
        </p>
        {goldCandidates.length === 0 ? (
          <p className={styles.emptySources}>
            This answer has no selectable citations. You can still save the
            case.
          </p>
        ) : (
          <ul className={styles.sourceList}>
            {goldCandidates.map((citation) => {
              const chunkId = citation.chunk_id as string;
              const checked = sheet.selectedChunkIds.includes(chunkId);
              const blocked = atCap && !checked;
              return (
                <li key={citation.citation_id}>
                  <label
                    className={
                      checked ? styles.sourceLabelSelected : styles.sourceLabel
                    }
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={blocked}
                      aria-disabled={blocked ? true : undefined}
                      onChange={() => sheet.onToggleChunk(chunkId)}
                    />
                    <UserText value={citationSourceLabel(citation)} />
                  </label>
                </li>
              );
            })}
          </ul>
        )}
        {atCap ? (
          <p className={styles.muted} role="status">
            Maximum 3 sources selected. Remove one to choose another.
          </p>
        ) : null}
      </fieldset>
      <p className={styles.helper}>
        This creates a development draft. It does not approve or score this
        answer.
      </p>
      <p className={styles.helper}>{QUIZ_RETENTION_DISCLOSURE}</p>
      <div className={styles.footer}>
        {sheet.saveError ? (
          <StatusBanner kind="error" role="alert" autoFocus={false}>
            {sheet.saveError}
          </StatusBanner>
        ) : null}
        {!sheet.saveError && sheet.saveNotice ? (
          <StatusBanner kind="success" role="status">
            {sheet.saveNotice}
          </StatusBanner>
        ) : null}
        <div className={styles.footerActions}>
          <Button
            type="button"
            variant="primary"
            data-action-id="ask.quiz.submit"
            pending={sheet.savePending}
            pendingLabel="Saving…"
            onClick={sheet.onSave}
          >
            Save quiz case
          </Button>
          {sheet.saveNotice ? (
            <Button type="button" variant="secondary" onClick={onViewSaved}>
              View saved cases
            </Button>
          ) : null}
        </div>
      </div>
    </>
  );
}

/**
 * Saved-tab list, detail-after-select, and guarded score/ask actions.
 *
 * @param sheet - Controlled list/detail fields from `useQuizCapture`.
 * @param onAsk - Ask-this-question handler that also closes the sheet.
 * @param onCreate - Switch to New case from the empty state.
 * @returns Saved-cases panel. Summaries never include question or expected text.
 */
function SavedCasesPanel({
  sheet,
  onAsk,
  onCreate,
}: {
  sheet: SaveToQuizSheetProps;
  onAsk: () => void;
  onCreate: () => void;
}) {
  return (
    <>
      <p className={styles.lead}>
        Reuse a saved question or compare this answer with an approved matching
        case.
      </p>
      {sheet.casesPending ? (
        <div className={styles.section}>
          <p className={styles.muted} role="status">
            Loading saved cases…
          </p>
          <ul className={styles.skeletonList} aria-hidden="true">
            <li className={styles.skeletonRow} />
            <li className={styles.skeletonRow} />
            <li className={styles.skeletonRow} />
          </ul>
        </div>
      ) : null}
      {!sheet.casesPending && sheet.casesError ? (
        <div className={styles.section}>
          <StatusBanner kind="error" role="alert" autoFocus={false}>
            Saved cases could not load.
          </StatusBanner>
          <Button type="button" variant="secondary" onClick={sheet.onRetryCases}>
            Retry
          </Button>
        </div>
      ) : null}
      {!sheet.casesPending && !sheet.casesError && sheet.cases.length === 0 ? (
        <EmptyState
          title="No saved cases yet"
          body="Save the current question to create the first draft."
          action={
            <Button type="button" variant="secondary" onClick={onCreate}>
              Create a case
            </Button>
          }
        />
      ) : null}
      {!sheet.casesPending && !sheet.casesError && sheet.cases.length > 0 ? (
        <ul className={styles.caseList} aria-label="Saved quiz cases">
          {sheet.cases.map((item) => {
            const current = item.case_id === sheet.selectedCaseId;
            const reviewLabel = reviewStatusLabel(
              item.review_status,
              item.human_approved,
            );
            return (
              <li key={item.case_id}>
                <button
                  type="button"
                  className={
                    current ? styles.caseButtonCurrent : styles.caseButton
                  }
                  aria-current={current ? "true" : undefined}
                  onClick={() => sheet.onSelectCase(item.case_id)}
                >
                  <span className={styles.caseTitle}>
                    <UserText value={queryClassLabel(item.query_class)} />
                  </span>
                  <span className={styles.caseMeta}>
                    <StatusPill
                      status={reviewLabel}
                      tone={reviewStatusTone(
                        item.review_status,
                        item.human_approved,
                      )}
                    />
                    <Badge label={sourceCountLabel(item.gold_chunk_count)} />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
      {sheet.nextCaseId && !sheet.casesPending && !sheet.casesError ? (
        <div className={styles.section}>
          {sheet.loadMoreError ? (
            <p className={styles.muted} role="status">
              More cases could not load. Try again.
            </p>
          ) : null}
          <Button
            type="button"
            data-action-id="ask.quiz.load_more"
            pending={sheet.loadMorePending}
            pendingLabel="Loading…"
            onClick={sheet.onLoadMore}
          >
            Load more
          </Button>
        </div>
      ) : null}
      {!sheet.casesPending && !sheet.casesError && sheet.cases.length > 0 ? (
        <SelectedCaseDetail sheet={sheet} onAsk={onAsk} />
      ) : null}
    </>
  );
}

/**
 * Detail-after-select card. Question text loads only after a row is chosen.
 *
 * @param sheet - Controlled detail and score fields.
 * @param onAsk - Ask-this-question handler that also closes the sheet.
 * @returns Instruction, pending, error, or selected-question actions.
 */
function SelectedCaseDetail({
  sheet,
  onAsk,
}: {
  sheet: SaveToQuizSheetProps;
  onAsk: () => void;
}) {
  if (sheet.selectedCaseId === null) {
    return (
      <p className={styles.instruction}>
        Select a case to preview its question and available actions.
      </p>
    );
  }
  if (sheet.detailPending) {
    return (
      <div className={styles.section}>
        <p className={styles.muted} role="status">
          Loading case…
        </p>
        <div className={styles.skeletonRow} aria-hidden="true" />
      </div>
    );
  }
  if (sheet.detailError) {
    return (
      <div className={styles.section}>
        <StatusBanner kind="error" role="alert" autoFocus={false}>
          This case could not load.
        </StatusBanner>
        <Button type="button" variant="secondary" onClick={sheet.onRetryDetail}>
          Retry
        </Button>
      </div>
    );
  }
  if (sheet.selectedQuestion === "") {
    return null;
  }
  return (
    <div className={styles.detailCard}>
      <h3 className={styles.sectionLabel}>Selected question</h3>
      <p className={styles.questionText}>
        <UserText value={sheet.selectedQuestion} />
      </p>
      <div className={styles.detailActions}>
        <Button
          type="button"
          data-action-id="ask.quiz.ask_question"
          onClick={onAsk}
        >
          Ask this question
        </Button>
        <Button
          type="button"
          data-action-id="ask.quiz.score"
          disabled={!sheet.scoreAllowed}
          disabledReason={
            sheet.scoreAllowed
              ? undefined
              : sheet.scoreReason ||
                `Score this answer only for a pre-existing approved case. ${QUIZ_SCORE_NOT_RECALL_LABEL}`
          }
          pending={sheet.scorePending}
          pendingLabel="Scoring…"
          onClick={sheet.onScore}
        >
          Score this answer ({QUIZ_SCORE_NOT_RECALL_LABEL})
        </Button>
      </div>
      {sheet.scoreError ? (
        <StatusBanner kind="error" role="alert" autoFocus={false}>
          {sheet.scoreError}
        </StatusBanner>
      ) : null}
      {!sheet.scoreError && sheet.scoreNotice ? (
        <StatusBanner kind="success" role="status">
          {sheet.scoreNotice}
        </StatusBanner>
      ) : null}
    </div>
  );
}
