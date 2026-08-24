/**
 * Dense data table with 48px enterprise rows.
 */

import type { ReactNode } from "react";
import { UserText } from "./user-text";
import styles from "./ui.module.css";

export type DataTableColumn<T> = {
  /** Stable column id. */
  id: string;
  /** English header. */
  header: string;
  /** Cell renderer. Hostile values must go through `UserText`. */
  cell: (row: T) => ReactNode;
  /** Numeric columns use end alignment and tabular numerals. */
  align?: "start" | "end";
};

export type DataTableProps<T> = {
  /** Accessible table caption. */
  caption: string;
  /** Column definitions. */
  columns: ReadonlyArray<DataTableColumn<T>>;
  /** Row data. */
  rows: ReadonlyArray<T>;
  /** Row identity. */
  getRowId: (row: T) => string;
};

/**
 * Render a sortable-looking static table. Sorting is a later packet.
 *
 * @typeParam T - Row type.
 * @param props - Caption, columns, rows.
 * @returns Table with `min-height: 48px` rows.
 * @remarks
 * Security: this component does not escape renderer output. Prefer
 * `UserText` in `cell`. Not an authorization boundary.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  getRowId,
}: DataTableProps<T>) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.id}
                scope="col"
                className={column.align === "end" ? styles.tableNumeric : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={getRowId(row)}>
              {columns.map((column) => (
                <td
                  key={column.id}
                  className={column.align === "end" ? styles.tableNumeric : undefined}
                >
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export { UserText };
