/**
 * Result-column and export guards. The client never totals numeric cells.
 */

import { isInternalColumnId } from "./validate";

/**
 * Collect allow-listed result column ids. Non-identifiers are omitted.
 *
 * @param rows - Analyze rows.
 * @returns Stable column order from the first row, plus later new keys.
 */
export function allowListedResultColumns(
  rows: ReadonlyArray<Record<string, unknown>>,
): { columns: string[]; omitted: boolean } {
  const columns: string[] = [];
  const seen = new Set<string>();
  let omitted = false;
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (key === "__row_id") {
        continue;
      }
      if (!isInternalColumnId(key)) {
        omitted = true;
        continue;
      }
      if (!seen.has(key)) {
        seen.add(key);
        columns.push(key);
      }
    }
  }
  return { columns, omitted };
}

/**
 * Return whether a cell should use numeric alignment.
 *
 * @param value - Cell value.
 * @returns True for finite numbers.
 */
export function isNumericTableCell(value: unknown): boolean {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Intentionally absent: the client must not sum displayed numeric cells.
 *
 * @returns Always `null` so tests can lock the contract.
 */
export function clientComputedTableTotal(): null {
  return null;
}

/**
 * Return whether an optional-tool disclosure listed a table export tool.
 *
 * `/tables` has no disclosure and must not render Export regardless.
 *
 * @param toolKeys - `optional_tool_disclosure.tool_keys` from the current run.
 * @returns True only for catalog export keys on a disclosed chat run.
 */
export function tableExportAllowed(toolKeys: readonly string[]): boolean {
  const exportKeys = new Set(["export_csv", "export_xlsx", "export_parquet"]);
  return toolKeys.some((key) => exportKeys.has(key));
}
