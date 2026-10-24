/**
 * Guided TableQueryPlan builder. No SQL editor, Export, Save, or Share.
 */

"use client";

import Link from "next/link";
import type { TablePlanDraft } from "../../lib/table-plan";
import type { TableManifestResponse } from "../../lib/types";
import { Button, PrimaryAction } from "../ui/button";
import { UserText } from "../ui/user-text";
import { AggregationsSection } from "./analysis-plan/aggregations-section";
import { ColumnsSection } from "./analysis-plan/columns-section";
import { ComparisonSection } from "./analysis-plan/comparison-section";
import { FiltersSection } from "./analysis-plan/filters-section";
import { GroupSortSection } from "./analysis-plan/group-sort-section";
import styles from "./tables.module.css";

export type AnalysisPlanProps = {
  /** Currently selected accessible table. */
  selected: TableManifestResponse | null;
  /** Document title from `GET /documents/{id}`, or the document id. */
  documentName: string;
  /** Guided draft. Preserved across analyze failures. */
  draft: TablePlanDraft;
  /** Analyze in flight. */
  pending: boolean;
  /** Replace the draft. */
  onDraftChange: (draft: TablePlanDraft) => void;
  /** Run a bounded deterministic row count. */
  onCountRows: () => void;
  /** Reset just the analysis draft. */
  onReset: () => void;
  /** Compile and POST. */
  onAnalyze: () => void;
};

/**
 * Render the Analysis plan card.
 *
 * @param props - Manifests, draft, and Analyze handler.
 * @returns Plan form. Does not fetch.
 */
export function AnalysisPlan({
  selected,
  documentName,
  draft,
  pending,
  onDraftChange,
  onAnalyze,
  onCountRows,
  onReset,
}: AnalysisPlanProps) {
  /**
   * Patch the draft immutably.
   *
   * @param patch - Partial draft.
   */
  function patchDraft(patch: Partial<TablePlanDraft>): void {
    onDraftChange({ ...draft, ...patch });
  }

  return (
    <section className={styles.card} aria-label="Analysis plan">
      <h2>Work with this table</h2>
      <p className={styles.muted}>Start with a row count, or build a calculation using the options below.</p>
      {selected ? <h3 className={styles.tableTitle}><UserText value={selected.sheet_name || selected.table_name.replace(/_/g, " ")} /></h3> : null}
      {selected ? (
        <p className={styles.muted}>
          From{" "}
          <Link
            href={`/documents/${encodeURIComponent(selected.document_id)}`}
            className={styles.documentLink}
          >
            <UserText value={documentName} />
          </Link>
        </p>
      ) : null}
      <div className={styles.quickActions}>
        <Button type="button" variant="primary" pending={pending} pendingLabel="Calculating..." disabled={selected === null} onClick={onCountRows}>Count rows</Button>
        <span className={styles.muted}>Counts the full selected table, without applying analysis filters.</span>
      </div>
      <details className={styles.analysisOptions}>
        <summary>Customize analysis</summary>
        <div className={styles.optionsBody}>
      <p className={styles.muted}>Use the exact column names from the original spreadsheet. Add a filter, calculation, grouping, sort, or comparison before analyzing.</p>
      <ColumnsSection columns={draft.columns} patchDraft={patchDraft} />
      <FiltersSection filters={draft.filters} patchDraft={patchDraft} />
      <AggregationsSection
        aggregations={draft.aggregations}
        patchDraft={patchDraft}
      />
      <GroupSortSection
        groupBy={draft.groupBy}
        sorts={draft.sorts}
        patchDraft={patchDraft}
      />
      <ComparisonSection draft={draft} patchDraft={patchDraft} />
        </div>
      <div className={styles.planActions}>
        <Button type="button" variant="secondary" disabled={pending} onClick={onReset}>Reset analysis</Button>
        <PrimaryAction
          type="button"
          data-action-id="tables.analyze"
          pending={pending}
          pendingLabel="Analyzing…"
          disabled={selected === null}
          disabledReason={
            selected === null ? "Select an available table." : undefined
          }
          onClick={onAnalyze}
        >
          Analyze
        </PrimaryAction>
      </div>
      </details>
    </section>
  );
}
