/**
 * Admin Recall@10 scoreboard, exam progress, and qualification confirmation.
 */

"use client";

import type { ApiAuth } from "../../lib/api";
import {
  examRecallHeadline,
  EXAM_RECALL_METRIC_NAME,
  isExamActive,
  isExamTerminal,
  shortEvalHash,
} from "../../lib/eval-workspace";
import { Button, PrimaryAction } from "../ui/button";
import { ConfirmDialog } from "../ui/confirm-dialog";
import { EmptyState } from "../ui/empty-state";
import { Select } from "../ui/select";
import { Spinner } from "../ui/spinner";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import tableStyles from "../admin/admin-tables.module.css";
import {
  datasetLabel,
  examRecallPercent,
  examStatusLabel,
  formatExamCompletedAt,
  sourceCountLabel,
} from "./evaluation-presenters";
import { useEvalExam } from "./hooks/use-eval-exam";
import styles from "./evaluation.module.css";

export type EvaluationExamBoardProps = {
  /** Owner/admin bearer auth. */
  auth: ApiAuth;
  /** Workspace approved-count for sample sufficiency. */
  approvedCount?: number;
  /** Open a report case in the editor. */
  onOpenCase: (caseId: string) => void;
};

const SPLIT_OPTIONS = [
  { value: "development", label: "Development" },
  { value: "qualification", label: "Qualification" },
] as const;

const CASE_FILTERS = [
  { value: "all", label: "All scored cases" },
  { value: "hit", label: "Hits" },
  { value: "miss", label: "Misses" },
] as const;

/**
 * Render the official production-corpus Recall@10 scoreboard.
 *
 * @param props - Auth, sample approved count, and case-editor callback.
 * @returns Scoreboard. Citation overlap is never labelled Recall@10.
 */
export function EvaluationExamBoard({
  auth,
  approvedCount = 0,
  onOpenCase,
}: EvaluationExamBoardProps) {
  const exam = useEvalExam({ auth, onOpenCase });
  const report = exam.report;
  const active = exam.exam && isExamActive(exam.exam.status);
  const terminal = exam.exam && isExamTerminal(exam.exam.status);
  const progress = exam.exam
    ? `${exam.exam.split} exam ${exam.exam.status}: ${String(exam.exam.completed_case_count)} of ${String(exam.exam.case_count)} cases.`
    : null;
  const present =
    report?.present === true &&
    report.hit_count !== null &&
    report.case_count !== null &&
    report.gates_pass !== null;
  const percent = present
    ? examRecallPercent({
        hitCount: report.hit_count as number,
        caseCount: report.case_count as number,
        ratio: report.hybrid_recall_at_10,
      })
    : 0;
  const progressWidth =
    exam.exam && exam.exam.case_count > 0
      ? Math.round((exam.exam.completed_case_count / exam.exam.case_count) * 100)
      : 0;

  return (
    <section className={styles.examBoard} aria-label="Recall@10 scoreboard">
      <h3>Official Recall@10</h3>
      <Select
        label="Report split"
        value={exam.split}
        options={[...SPLIT_OPTIONS]}
        onChange={(event) => {
          const value = event.target.value;
          if (value === "development" || value === "qualification") {
            exam.onSplit(value);
          }
        }}
      />
      {exam.reportPending ? <Spinner label="Loading official report" /> : null}
      {report && !report.present ? (
        <EmptyState
          title="No official result yet"
          body="Run the development exam after approved cases have current required sources."
          action={
            <>
              <PrimaryAction
                type="button"
                data-action-id="eval.exam_start_development"
                pending={exam.startPending}
                pendingLabel="Starting…"
                onClick={exam.onStartDevelopment}
              >
                Run development exam
              </PrimaryAction>
              <Button
                type="button"
                data-action-id="eval.exam_start_qualification"
                onClick={exam.onOpenQualification}
              >
                Run qualification exam
              </Button>
            </>
          }
        />
      ) : null}
      {present ? (
        <div className={styles.card}>
          <p className={tableStyles.metricValue}>{`${String(percent)}%`}</p>
          <p>
            {`${String(report.hit_count)} of ${String(report.case_count)} cases found every required source`}
          </p>
          <p>
            {examRecallHeadline({
              hitCount: report.hit_count as number,
              caseCount: report.case_count as number,
              ratio: report.hybrid_recall_at_10,
            })}
          </p>
          {report.gates_pass ? (
            <StatusPill status="Retrieve gates passed." tone="success" />
          ) : (
            <p role="status">
              Degraded or failed retrieve gates. Official Recall@10 did not
              pass.
            </p>
          )}
          <p className={styles.muted}>
            {`${datasetLabel(report.split ?? "")}. Completed ${formatExamCompletedAt(report.created_at)}. Sample ${String(report.case_count)} labeled cases (${String(approvedCount)} approved in the workspace).`}
          </p>
        </div>
      ) : null}
      <details>
        <summary>What Recall@10 means</summary>
        <p className={styles.muted}>
          {EXAM_RECALL_METRIC_NAME} for the signed-in examiner. Citation overlap
          from Ask or Compare citations is not Recall@10. Holdout stays out.
        </p>
      </details>
      <details>
        <summary>Technical details</summary>
        <p className={styles.muted}>
          Dataset {shortEvalHash(report?.dataset_hash ?? exam.exam?.dataset_hash)}.
          {exam.exam
            ? ` Candidate ${shortEvalHash(exam.exam.candidate_fingerprint)}.`
            : null}
        </p>
      </details>
      {exam.emptyDataset ? (
        <StatusBanner kind="warning" role="status">
          {`Not enough approved current gold to start an exam. Approved ${String(exam.emptyDataset.approved_count)}, drafts ${String(exam.emptyDataset.draft_count)}, stale gold ${String(exam.emptyDataset.stale_gold_count)}.`}
        </StatusBanner>
      ) : null}
      {exam.startError ? (
        <StatusBanner kind="error" role="status">
          {exam.startError}
        </StatusBanner>
      ) : null}
      {exam.canResume ? (
        <Button type="button" data-action-id="eval.exam_resume" onClick={exam.onResume}>
          Resume progress
        </Button>
      ) : null}
      {exam.exam ? (
        <p className={styles.muted}>
          {examStatusLabel(exam.exam.status)}
        </p>
      ) : null}
      {progress ? (
        <p className={styles.muted} aria-live="polite">
          {progress}
        </p>
      ) : null}
      {active && exam.exam ? (
        <div className={styles.progressTrack} aria-hidden="true">
          <span
            className={styles.progressFill}
            style={{ width: `${String(progressWidth)}%` }}
          />
        </div>
      ) : null}
      {terminal && exam.exam?.status !== "succeeded" ? (
        <p className={styles.muted} role="status">
          {`The ${exam.exam?.status} exam did not replace the official report.`}
        </p>
      ) : null}
      {present ? (
        <div className={styles.actions}>
          <PrimaryAction
            type="button"
            data-action-id="eval.exam_start_development"
            pending={exam.startPending}
            pendingLabel="Starting…"
            onClick={exam.onStartDevelopment}
          >
            Run development exam
          </PrimaryAction>
          <Button
            type="button"
            data-action-id="eval.exam_start_qualification"
            onClick={exam.onOpenQualification}
          >
            Run qualification exam
          </Button>
        </div>
      ) : null}
      {active ? (
        <Button
          type="button"
          data-action-id="eval.exam_cancel"
          pending={exam.cancelPending}
          pendingLabel="Cancelling…"
          onClick={exam.onCancel}
        >
          Cancel exam
        </Button>
      ) : null}
      {exam.qualificationOpen ? (
        <ConfirmDialog
          title="Start the one qualification exam?"
          confirmLabel="Start qualification"
          onClose={exam.onCloseQualification}
          onConfirm={exam.onConfirmQualification}
        >
          This dataset and candidate can be examined once. The server remains
          authoritative. Holdout stays out.
        </ConfirmDialog>
      ) : null}
      {present ? (
        <div>
          <Select
            label="Scored cases"
            value={exam.caseFilter}
            options={[...CASE_FILTERS]}
            onChange={(event) => {
              const value = event.target.value;
              if (value === "all" || value === "hit" || value === "miss") {
                exam.onCaseFilter(value);
              }
            }}
          />
          <p className={styles.muted}>
            {`${String(exam.missedCount)} missed cases. Rows are counts only.`}
          </p>
          <ul className={styles.caseList}>
            {exam.visibleCases.map((item) => (
              <li key={item.case_id}>
                <button
                  type="button"
                  className={styles.caseButton}
                  data-action-id="eval.exam_open_case"
                  onClick={() => exam.onOpenCase(item.case_id)}
                >
                  {`Open case ${String(item.ordinal)} · ${item.hit ? "hit" : "miss"} · ${sourceCountLabel(item.gold_count)} · ${String(item.ranked_hit_count)} in top 10`}
                  <StatusPill
                    status={item.hit ? "Hit" : "Miss"}
                    tone={item.hit ? "success" : "warning"}
                  />
                </button>
              </li>
            ))}
          </ul>
          {exam.caseNext ? (
            <Button
              type="button"
              data-action-id="eval.exam_cases_more"
              onClick={exam.onLoadMoreCases}
            >
              Load more scored cases
            </Button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
