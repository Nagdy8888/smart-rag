/**
 * Guided TableQueryPlan builder. No SQL editor, Export, Save, or Share.
 */

"use client";

import Link from "next/link";
import type { TablePlanDraft } from "../../lib/table-plan";
import type { TableManifestResponse } from "../../lib/types";
import { PrimaryAction } from "../ui/button";
import { Select } from "../ui/select";
import { UserText } from "../ui/user-text";
import { AggregationsSection } from "./analysis-plan/aggregations-section";
import { ColumnsSection } from "./analysis-plan/columns-section";
import { ComparisonSection } from "./analysis-plan/comparison-section";
import { FiltersSection } from "./analysis-plan/filters-section";
import { GroupSortSection } from "./analysis-plan/group-sort-section";
import styles from "./tables.module.css";

export type AnalysisPlanProps = {
  /** Authorized manifests. */
  manifests: readonly TableManifestResponse[];
  /** Currently selected accessible table. */
  selected: TableManifestResponse | null;
  /** Document title from `GET /documents/{id}`, or the document id. */
  documentName: string;
  /** Guided draft. Preserved across analyze failures. */
  draft: TablePlanDraft;
  /** Analyze in flight. */
  pending: boolean;
  /** Sidebar/select change. */
  onSelectTableId: (tableId: string) => void;
  /** Replace the draft. */
  onDraftChange: (draft: TablePlanDraft) => void;
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
  manifests,
  selected,
  documentName,
  draft,
  pending,
  onSelectTableId,
  onDraftChange,
  onAnalyze,
}: AnalysisPlanProps) {
  const tableOptions = [
    { value: "", label: "Select a table", disabled: true },
    ...manifests.map((item) => ({
      value: item.table_id,
      label: item.sheet_name
        ? `${item.table_name} (${item.sheet_name})`
        : item.table_name,
    })),
  ];

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
      <h2>Analysis plan</h2>
      <Select
        label="Table"
        value={selected?.table_id ?? ""}
        options={tableOptions}
        onChange={(event) => onSelectTableId(event.target.value)}
      />
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
      <div className={styles.planActions}>
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
    </section>
  );
}
