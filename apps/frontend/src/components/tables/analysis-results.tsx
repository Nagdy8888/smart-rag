/**
 * Deterministic analyze results, display-only sort, and cell provenance.
 */

"use client";

import { useState } from "react";
import { Button } from "../ui/button";
import { CodeText, UserText } from "../ui/user-text";
import { DataTable } from "../ui/data-table";
import { Select } from "../ui/select";
import { Sheet } from "../ui/sheet";
import {
  DISPLAY_SORT_LABEL,
  EMPTY_ANALYZE_ROWS_COPY,
  OMITTED_RESULT_COLUMN_COPY,
  allowListedResultColumns,
  isNumericTableCell,
} from "../../lib/table-plan";
import type { TableAnalyzeResponse, TableManifestResponse } from "../../lib/types";
import { StatusBanner } from "../ui/status-banner";
import styles from "./tables.module.css";

export type AnalysisResultsProps = {
  /** Analyze HTTP body. */
  result: TableAnalyzeResponse;
  /** Manifest used for sheet identity. */
  selected: TableManifestResponse | null;
  /** Client display sort key. */
  displaySortKey: string | null;
  /** Client display sort direction. */
  displaySortDir: "asc" | "desc";
  /** Change display sort key. */
  onDisplaySortKey: (key: string | null) => void;
  /** Change display sort direction. */
  onDisplaySortDir: (dir: "asc" | "desc") => void;
};

/**
 * Render deterministic rows, display-only sort, and the provenance drawer.
 *
 * @param props - Result, plan, and display-sort state.
 * @returns Results card. Does not fetch.
 */
export function AnalysisResults({
  result,
  selected,
  displaySortKey,
  displaySortDir,
  onDisplaySortKey,
  onDisplaySortDir,
}: AnalysisResultsProps) {
  const [provenanceOpen, setProvenanceOpen] = useState(false);
  const listed = allowListedResultColumns(result.rows);
  const sortedRows = [...result.rows].sort((left, right) => {
    if (displaySortKey === null) {
      return 0;
    }
    const a = String(left[displaySortKey] ?? "");
    const b = String(right[displaySortKey] ?? "");
    const cmp = a.localeCompare(b);
    return displaySortDir === "asc" ? cmp : -cmp;
  });
  const indexedRows = sortedRows.map((row, index) => ({
    ...row,
    __row_id: String(index),
  }));
  const hasRanges = result.source_ranges.length > 0;
  const numericColumns = new Set(
    listed.columns.filter((column) =>
      result.rows.some((row) => isNumericTableCell(row[column])),
    ),
  );

  return (
    <section className={styles.card} aria-label="Results">
      <div className={styles.resultsHeader}>
        <h2>Results</h2>
        <p className={styles.muted}>{result.rows.length} rows</p>
        {hasRanges ? (
          <Button type="button" onClick={() => setProvenanceOpen(true)}>
            View provenance
          </Button>
        ) : null}
      </div>
      {listed.omitted ? (
        <StatusBanner kind="warning">{OMITTED_RESULT_COLUMN_COPY}</StatusBanner>
      ) : null}
      {result.rows.length === 0 ? (
        <p className={styles.muted}>{EMPTY_ANALYZE_ROWS_COPY}</p>
      ) : listed.columns.length === 0 ? (
        <p className={styles.muted}>{OMITTED_RESULT_COLUMN_COPY}</p>
      ) : (
        <>
          <div className={styles.sortRow}>
            <Select
              label={DISPLAY_SORT_LABEL}
              value={displaySortKey ?? ""}
              options={[
                { value: "", label: "None" },
                ...listed.columns.map((column) => ({
                  value: column,
                  label: column,
                })),
              ]}
              onChange={(event) =>
                onDisplaySortKey(event.target.value === "" ? null : event.target.value)
              }
            />
            <Button
              type="button"
              aria-label="Toggle display sort direction"
              onClick={() =>
                onDisplaySortDir(displaySortDir === "asc" ? "desc" : "asc")
              }
            >
              {displaySortDir}
            </Button>
          </div>
          <DataTable
            caption="Table analyze rows"
            columns={listed.columns.map((id) => ({
              id,
              header: id,
              align: numericColumns.has(id) ? "end" : "start",
              cell: (row: Record<string, unknown>) => (
                <UserText
                  value={row[id]}
                  className={numericColumns.has(id) ? styles.numeric : undefined}
                />
              ),
            }))}
            rows={indexedRows}
            getRowId={(row) => String(row.__row_id)}
          />
        </>
      )}
      {provenanceOpen ? (
        <Sheet title="Cell provenance" onClose={() => setProvenanceOpen(false)}>
          <dl className={styles.dl}>
            <dt>document_id</dt>
            <dd>
              <CodeText value={result.document_id} />
            </dd>
            <dt>version_id</dt>
            <dd>
              <CodeText value={result.version_id} />
            </dd>
            <dt>table_id</dt>
            <dd>
              <CodeText value={result.table_id} />
            </dd>
            <dt>sheet</dt>
            <dd>
              <UserText value={selected?.sheet_name ?? "none"} />
            </dd>
            <dt>ranges</dt>
            <dd>
              <ul className={styles.rangeList}>
                {result.source_ranges.map((range) => (
                  <li key={range} className={styles.mono}>
                    <CodeText value={range} />
                  </li>
                ))}
              </ul>
            </dd>
          </dl>
        </Sheet>
      ) : null}
    </section>
  );
}
