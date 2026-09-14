/**
 * Evaluation Overview: readiness metrics and the next recommended task.
 */

"use client";

import type { PdfEvalStatus } from "../../lib/types";
import { Button, PrimaryAction } from "../ui/button";
import { EmptyState } from "../ui/empty-state";
import { Select } from "../ui/select";
import { StatusBanner } from "../ui/status-banner";
import tableStyles from "../admin/admin-tables.module.css";
import { metricCount, overviewGuidanceKind } from "./evaluation-presenters";
import styles from "./evaluation.module.css";

export type EvaluationOverviewProps = {
  /** Workspace status counts. Optional fields may be absent. */
  status: PdfEvalStatus | undefined;
  /** Current documents for draft generation. */
  documentOptions: ReadonlyArray<{ value: string; label: string }>;
  /** Selected document ID for regeneration. */
  regenDocumentId: string;
  /** Select a document. */
  onRegenDocumentChange: (documentId: string) => void;
  /** Regeneration pending. */
  regeneratePending: boolean;
  /** Start document-scoped unapproved drafts. */
  onRegenerate: () => void;
  /** Latest regeneration notice. */
  regenNotice: string | null;
  /** Open Review cases with the stale-source filter. */
  onReviewStale: () => void;
  /** Open Review cases on the next draft or stale row. */
  onReviewNext: () => void;
  /** Open Exam results without starting an exam. */
  onViewResults: () => void;
};

/**
 * Render Overview metrics and task-aware guidance.
 *
 * @param props - Status, regenerate controls, and navigation callbacks.
 * @returns Overview panel. Never starts a paid exam.
 */
export function EvaluationOverview({
  status,
  documentOptions,
  regenDocumentId,
  onRegenDocumentChange,
  regeneratePending,
  onRegenerate,
  regenNotice,
  onReviewStale,
  onReviewNext,
  onViewResults,
}: EvaluationOverviewProps) {
  const kind = overviewGuidanceKind(status);
  const staleCount = status?.stale_gold_count;
  const generate = (
    <>
      {documentOptions.length > 0 ? (
        <Select
          label="Regenerate document"
          value={regenDocumentId}
          options={[...documentOptions]}
          onChange={(event) => onRegenDocumentChange(event.target.value)}
        />
      ) : null}
      <Button
        type="button"
        data-action-id="eval.regenerate"
        pending={regeneratePending}
        pendingLabel="Regenerating…"
        disabled={regenDocumentId === ""}
        disabledReason={
          regenDocumentId === "" ? "Select a current document first." : undefined
        }
        onClick={onRegenerate}
      >
        Generate review cases
      </Button>
    </>
  );

  return (
    <div
      role="tabpanel"
      id="eval-panel-overview"
      aria-labelledby="eval-tab-overview"
      className={styles.taskPanel}
    >
      <div className={tableStyles.metricGrid}>
        <section className={tableStyles.metricCard} aria-label="Draft cases">
          <p className={tableStyles.metricLabel}>Draft cases</p>
          <p className={tableStyles.metricValue}>{metricCount(status?.draft_count)}</p>
        </section>
        <section className={tableStyles.metricCard} aria-label="Approved cases">
          <p className={tableStyles.metricLabel}>Approved cases</p>
          <p className={tableStyles.metricValue}>{metricCount(status?.approved_count)}</p>
        </section>
        <section className={tableStyles.metricCard} aria-label="Stale sources">
          <p className={tableStyles.metricLabel}>Stale sources</p>
          <p className={tableStyles.metricValue}>{metricCount(staleCount)}</p>
          {typeof staleCount === "number" && staleCount > 0 ? (
            <p className={styles.muted}>Repair these sources before an exam.</p>
          ) : null}
        </section>
        <section className={tableStyles.metricCard} aria-label="Remaining slots">
          <p className={tableStyles.metricLabel}>Remaining slots</p>
          <p className={tableStyles.metricValue}>
            {metricCount(status?.remaining_capacity)}
          </p>
        </section>
      </div>
      {regenNotice ? (
        <StatusBanner kind="success" role="status">
          {regenNotice}
        </StatusBanner>
      ) : null}
      {kind === "empty" ? (
        <EmptyState
          title="Create your first review set"
          body="Choose a document and generate draft questions. Drafts must be checked and approved by a person before they can be used in an exam."
          action={generate}
        />
      ) : (
        <section className={styles.card} aria-label="Generate review cases">
          <h3>Generate review cases</h3>
          <p className={styles.muted}>
            Drafts must be checked and approved by a person before they can be
            used in an exam.
          </p>
          {generate}
        </section>
      )}
      {kind === "stale" ? (
        <section className={styles.card}>
          <h3>Repair stale sources first</h3>
          <p className={styles.muted}>
            Required sources no longer match the current document version. Remap
            them before approval or an exam.
          </p>
          <PrimaryAction
            type="button"
            data-action-id="eval.review_next"
            onClick={onReviewStale}
          >
            Review stale cases
          </PrimaryAction>
        </section>
      ) : null}
      {kind === "drafts" ? (
        <section className={styles.card}>
          <h3>Cases are waiting for review</h3>
          <p className={styles.muted}>
            Approve only after the question and required sources are correct.
          </p>
          <PrimaryAction
            type="button"
            data-action-id="eval.review_next"
            onClick={onReviewNext}
          >
            Review next case
          </PrimaryAction>
        </section>
      ) : null}
      {kind === "ready" ? (
        <section className={styles.card}>
          <h3>The review set is ready</h3>
          <p className={styles.muted}>
            Official Recall@10 lives on Exam results. This button does not start
            an exam.
          </p>
          <PrimaryAction
            type="button"
            data-action-id="eval.view.results"
            onClick={onViewResults}
          >
            View exam results
          </PrimaryAction>
        </section>
      ) : null}
    </div>
  );
}
