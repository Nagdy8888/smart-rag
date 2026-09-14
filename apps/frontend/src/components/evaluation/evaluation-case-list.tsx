/**
 * Evaluation case queue: filters, private-safe rows, and pagination.
 */

"use client";

import type { EvalGoldStateFilter } from "../../lib/eval-workspace";
import type { PdfEvalCaseSummary } from "../../lib/types";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { EmptyState } from "../ui/empty-state";
import { Select } from "../ui/select";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import {
  DATASET_FILTER_OPTIONS,
  REVIEW_FILTER_OPTIONS,
  SOURCE_FILTER_OPTIONS,
  datasetLabel,
  queryClassLabel,
  reviewStatusLabel,
  reviewStatusTone,
  sourceCountLabel,
  sourceStatusLabel,
  sourceStatusTone,
} from "./evaluation-presenters";
import styles from "./evaluation.module.css";

export type EvaluationCaseListProps = {
  /** Dataset/split filter. */
  split: string;
  /** Review-status filter. */
  review: string;
  /** Client gold-state filter. */
  goldState: EvalGoldStateFilter;
  /** Change dataset filter. */
  onSplit: (value: string) => void;
  /** Change review filter. */
  onReview: (value: string) => void;
  /** Change source filter. */
  onGoldState: (value: EvalGoldStateFilter) => void;
  /** Restore all three filters to `all`. */
  onClearFilters: () => void;
  /** Filtered summaries. No questions. */
  items: readonly PdfEvalCaseSummary[];
  /** Selected case ID. */
  selected: string | null;
  /** Select a queue row. */
  onSelect: (caseId: string) => void;
  /** Next list cursor, or null. */
  nextCaseId: string | null;
  /** Load-more pending. */
  loadMorePending: boolean;
  /** Fetch the next page. */
  onLoadMore: () => void;
  /** True when the workspace has zero cases. */
  workspaceEmpty: boolean;
  /** Switch to Overview. */
  onGoOverview: () => void;
};

/**
 * Render filters and the case queue. Private question text is never shown.
 *
 * @param props - Filters, summaries, and pagination.
 * @returns Queue column.
 */
export function EvaluationCaseList({
  split,
  review,
  goldState,
  onSplit,
  onReview,
  onGoldState,
  onClearFilters,
  items,
  selected,
  onSelect,
  nextCaseId,
  loadMorePending,
  onLoadMore,
  workspaceEmpty,
  onGoOverview,
}: EvaluationCaseListProps) {
  return (
    <div className={styles.queue}>
      <div className={styles.filters}>
        <Select
          label="Dataset"
          value={split}
          options={[...DATASET_FILTER_OPTIONS]}
          onChange={(event) => onSplit(event.target.value)}
        />
        <Select
          label="Review status"
          value={review}
          options={[...REVIEW_FILTER_OPTIONS]}
          onChange={(event) => onReview(event.target.value)}
        />
        <Select
          label="Source status"
          value={goldState}
          options={[...SOURCE_FILTER_OPTIONS]}
          onChange={(event) => onGoldState(event.target.value as EvalGoldStateFilter)}
        />
      </div>
      <nav aria-label="Evaluation cases">
        {items.length === 0 && workspaceEmpty ? (
          <EmptyState
            title="No review cases yet"
            body="Generate draft questions from Overview, then review them here."
            action={
              <Button
                type="button"
                data-action-id="eval.view.overview"
                onClick={onGoOverview}
              >
                Go to Overview
              </Button>
            }
          />
        ) : null}
        {items.length === 0 && !workspaceEmpty ? (
          <EmptyState
            title="No cases match these filters"
            body="Clear the dataset, review, or source filters to see more cases."
            action={
              <Button
                type="button"
                data-action-id="eval.clear_filters"
                onClick={onClearFilters}
              >
                Clear filters
              </Button>
            }
          />
        ) : null}
        {items.length > 0 ? (
          <ul className={styles.caseList}>
            {items.map((item) => {
              const current = item.case_id === selected;
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
                    onClick={() => onSelect(item.case_id)}
                  >
                    <span className={styles.caseTitle}>
                      <UserText value={queryClassLabel(item.query_class)} />
                    </span>
                    <span className={styles.caseMeta}>
                      <Badge label={datasetLabel(item.split)} />
                      <StatusPill
                        status={reviewLabel}
                        tone={reviewStatusTone(item.review_status, item.human_approved)}
                      />
                      <StatusPill
                        status={sourceStatusLabel(item.gold_stale)}
                        tone={sourceStatusTone(item.gold_stale)}
                      />
                      <span className={styles.muted}>
                        {sourceCountLabel(item.gold_chunk_count)}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
        {nextCaseId ? (
          <Button
            type="button"
            data-action-id="eval.load_more"
            pending={loadMorePending}
            pendingLabel="Loading…"
            onClick={onLoadMore}
          >
            Load more
          </Button>
        ) : null}
      </nav>
    </div>
  );
}
