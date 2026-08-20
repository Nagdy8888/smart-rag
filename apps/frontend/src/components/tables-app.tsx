/**
 * Structured tables: list + typed plan builder + deterministic results.
 * No SQL textarea. No client-summed totals. No fake LLM commentary.
 * Export only after optional-tool disclosure on a chat run — this page has none.
 */

"use client";

import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Button } from "./ui/button";
import { DataTable } from "./ui/data-table";
import { Input } from "./ui/input";
import { UserText } from "./ui/user-text";
import { analyzeTable, listTables, type ApiAuth } from "../lib/api";
import { useSession } from "../lib/auth/session-provider";
import { sessionQueryKeys } from "../lib/query-keys";
import {
  TABLE_AGGREGATION_OPS,
  TABLE_PREDICATE_OPERATORS,
  TABLE_ROW_LIMIT_MAX,
  TABLE_SORT_DIRECTIONS,
  buildTableQueryPlan,
  clientComputedTableTotal,
  tableExportAllowed,
  type TablePredicateOperator,
  type TableSortDirection,
} from "../lib/table-plan";
import type { TableAggregationOp, TableManifestResponse } from "../lib/types";
import styles from "./developer-app.module.css";

/**
 * Tables list and analyze surface.
 *
 * @returns Tables UI.
 */
export function TablesApp() {
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const [selected, setSelected] = useState<TableManifestResponse | null>(null);
  const [column, setColumn] = useState("");
  const [operator, setOperator] =
    useState<TablePredicateOperator>("eq");
  const [predicateValue, setPredicateValue] = useState("");
  const [aggregation, setAggregation] = useState<TableAggregationOp>("count");
  const [aggColumn, setAggColumn] = useState("");
  const [sortColumn, setSortColumn] = useState("");
  const [sortDirection, setSortDirection] = useState<TableSortDirection>("asc");
  const [rowLimit, setRowLimit] = useState(100);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const tablesQuery = useQuery({
    queryKey: keys.tables,
    queryFn: () => listTables(auth as ApiAuth),
    enabled: auth !== null,
  });

  const analyzeMutation = useMutation({
    mutationFn: async () => {
      if (auth === null || selected === null) {
        throw new Error("no_table");
      }
      const plan = buildTableQueryPlan({
        table_id: selected.table_id,
        version_id: selected.version_id,
        predicates:
          column.trim() === ""
            ? []
            : [
                {
                  column: column.trim(),
                  operator,
                  value: predicateValue,
                },
              ],
        aggregations:
          aggregation === "count" || aggColumn.trim() !== ""
            ? [
                {
                  op: aggregation,
                  column: aggregation === "count" ? null : aggColumn.trim(),
                  alias: "result",
                },
              ]
            : [],
        order_by:
          sortColumn.trim() === ""
            ? []
            : [{ column: sortColumn.trim(), direction: sortDirection }],
        row_limit: rowLimit,
      });
      return analyzeTable(auth, plan);
    },
  });

  if (!session.ready || accessToken === null) {
    return (
      <div className={styles.shell}>
        <h1>Tables</h1>
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const rows = analyzeMutation.data?.rows ?? [];
  const columns = rows[0] !== undefined ? Object.keys(rows[0]) : [];
  const sortedRows = [...rows].sort((left, right) => {
    if (sortKey === null) {
      return 0;
    }
    const a = String(left[sortKey] ?? "");
    const b = String(right[sortKey] ?? "");
    const cmp = a.localeCompare(b);
    return sortDir === "asc" ? cmp : -cmp;
  });
  const indexedRows = sortedRows.map((row, index) => ({
    ...row,
    __row_id: String(index),
  }));

  return (
    <div className={styles.shell}>
      <h1>Structured tables</h1>
      <p className={styles.pageLead}>
        Deterministic results from authorized spreadsheets. This page has no
        generated commentary. Client total is{" "}
        {String(clientComputedTableTotal())}.
      </p>
      <section className={styles.panel} aria-label="Manifests">
        <h2>Authorized tables</h2>
        {(tablesQuery.data ?? []).length === 0 ? (
          <p className={styles.muted}>No authorized tables</p>
        ) : (
          <ul className={styles.list}>
            {(tablesQuery.data ?? []).map((item) => (
              <li key={item.table_id}>
                <button type="button" onClick={() => setSelected(item)}>
                  <UserText value={item.table_name} />
                  {item.sheet_name ? (
                    <>
                      {" "}
                      (<UserText value={item.sheet_name} />)
                    </>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      {selected ? (
        <section className={styles.panel} aria-label="Plan builder">
          <h2>Plan builder</h2>
          <p className={styles.muted}>
            table_id <UserText value={selected.table_id} /> version_id{" "}
            <UserText value={selected.version_id} />
          </p>
          <div className={styles.formGrid}>
            <Input
              label="Predicate column"
              value={column}
              onChange={(event) => setColumn(event.target.value)}
            />
            <label>
              Operator
              <select
                value={operator}
                onChange={(event) =>
                  setOperator(event.target.value as TablePredicateOperator)
                }
              >
                {TABLE_PREDICATE_OPERATORS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <Input
              label="Predicate value"
              value={predicateValue}
              onChange={(event) => setPredicateValue(event.target.value)}
            />
            <label>
              Aggregation
              <select
                value={aggregation}
                onChange={(event) =>
                  setAggregation(event.target.value as TableAggregationOp)
                }
              >
                {TABLE_AGGREGATION_OPS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <Input
              label="Aggregation column"
              value={aggColumn}
              onChange={(event) => setAggColumn(event.target.value)}
            />
            <Input
              label="Order column"
              value={sortColumn}
              onChange={(event) => setSortColumn(event.target.value)}
            />
            <label>
              Order
              <select
                value={sortDirection}
                onChange={(event) =>
                  setSortDirection(event.target.value as TableSortDirection)
                }
              >
                {TABLE_SORT_DIRECTIONS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <Input
              label="Row limit (max 1000)"
              type="number"
              min={1}
              max={TABLE_ROW_LIMIT_MAX}
              value={String(rowLimit)}
              onChange={(event) => setRowLimit(Number(event.target.value))}
            />
          </div>
          <Button
            type="button"
            variant="primary"
            onClick={() => analyzeMutation.mutate()}
          >
            Analyze
          </Button>
          {analyzeMutation.isError ? (
            <p className={styles.muted}>
              Plan rejected (422 extra fields or invalid plan).
            </p>
          ) : null}
        </section>
      ) : null}
      {analyzeMutation.data ? (
        <section className={styles.panel} aria-label="Deterministic results">
          <h2>Data execution</h2>
          <p className={styles.muted}>Deterministic rows from the typed plan.</p>
          {columns.length > 0 ? (
            <label>
              Sort displayed rows
              <select
                value={sortKey ?? ""}
                onChange={(event) => setSortKey(event.target.value || null)}
              >
                <option value="">none</option>
                {columns.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <Button
            type="button"
            onClick={() => setSortDir((prev) => (prev === "asc" ? "desc" : "asc"))}
          >
            {sortDir}
          </Button>
          <DataTable
            caption="Table analyze rows"
            columns={columns.map((id) => ({
              id,
              header: id,
              cell: (row: Record<string, unknown>) => (
                <UserText value={row[id]} />
              ),
            }))}
            rows={indexedRows}
            getRowId={(row) => String(row.__row_id)}
          />
          <p className={styles.muted}>
            source_ranges:{" "}
            <UserText
              value={analyzeMutation.data.source_ranges.join(", ") || "none"}
            />
          </p>
          {tableExportAllowed([]) ? (
            <Button type="button">Export</Button>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
