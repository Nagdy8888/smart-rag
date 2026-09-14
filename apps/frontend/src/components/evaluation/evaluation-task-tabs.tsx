/**
 * Accessible local tabs for Overview, Review cases, and Exam results.
 */

"use client";

import type { KeyboardEvent } from "react";
import { useRef } from "react";
import shellStyles from "../admin/admin-shell.module.css";
import {
  EVALUATION_VIEW_LABELS,
  EVALUATION_VIEWS,
  type EvaluationView,
} from "./evaluation-presenters";
import styles from "./evaluation.module.css";

export type EvaluationTaskTabsProps = {
  /** Active task view. */
  value: EvaluationView;
  /** Select a task view. */
  onChange: (view: EvaluationView) => void;
};

/**
 * Render the Evaluation task tablist. Only the selected panel should mount.
 *
 * @param props - Active view and change handler.
 * @returns Tablist. ArrowLeft/ArrowRight/Home/End move selection.
 */
export function EvaluationTaskTabs({ value, onChange }: EvaluationTaskTabsProps) {
  const refs = useRef<Partial<Record<EvaluationView, HTMLButtonElement | null>>>({});

  /**
   * Move among task tabs with arrows.
   *
   * @param event - Keyboard event from the focused tab.
   * @param index - Focused tab index.
   */
  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number): void {
    const last = EVALUATION_VIEWS.length - 1;
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
    const view = EVALUATION_VIEWS[next];
    if (view) {
      onChange(view);
      refs.current[view]?.focus();
    }
  }

  return (
    <div
      role="tablist"
      aria-label="Evaluation sections"
      className={`${shellStyles.tabList} ${styles.taskTabs}`}
    >
      <button
        type="button"
        role="tab"
        id="eval-tab-overview"
        aria-selected={value === "overview"}
        aria-controls="eval-panel-overview"
        tabIndex={value === "overview" ? 0 : -1}
        className={value === "overview" ? shellStyles.tabCurrent : shellStyles.tab}
        data-action-id="eval.view.overview"
        ref={(node) => {
          refs.current.overview = node;
        }}
        onClick={() => onChange("overview")}
        onKeyDown={(event) => onKeyDown(event, 0)}
      >
        {EVALUATION_VIEW_LABELS.overview}
      </button>
      <button
        type="button"
        role="tab"
        id="eval-tab-cases"
        aria-selected={value === "cases"}
        aria-controls="eval-panel-cases"
        tabIndex={value === "cases" ? 0 : -1}
        className={value === "cases" ? shellStyles.tabCurrent : shellStyles.tab}
        data-action-id="eval.view.cases"
        ref={(node) => {
          refs.current.cases = node;
        }}
        onClick={() => onChange("cases")}
        onKeyDown={(event) => onKeyDown(event, 1)}
      >
        {EVALUATION_VIEW_LABELS.cases}
      </button>
      <button
        type="button"
        role="tab"
        id="eval-tab-results"
        aria-selected={value === "results"}
        aria-controls="eval-panel-results"
        tabIndex={value === "results" ? 0 : -1}
        className={value === "results" ? shellStyles.tabCurrent : shellStyles.tab}
        data-action-id="eval.view.results"
        ref={(node) => {
          refs.current.results = node;
        }}
        onClick={() => onChange("results")}
        onKeyDown={(event) => onKeyDown(event, 2)}
      >
        {EVALUATION_VIEW_LABELS.results}
      </button>
    </div>
  );
}
