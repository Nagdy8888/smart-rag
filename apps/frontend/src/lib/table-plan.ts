/**
 * Extra-forbid TableQueryPlan builder. No SQL field. No client-side totals.
 */

import {
  TABLE_AGGREGATION_OPS,
  TABLE_PREDICATE_OPERATORS,
  TABLE_SORT_DIRECTIONS,
  type TableAggregationOp,
  type TablePredicate,
  type TablePredicateOperator,
  type TableQueryPlan,
  type TableSortDirection,
} from "./types";

/** Default `row_limit` from the schema. */
export const TABLE_ROW_LIMIT_DEFAULT = 100;

/** Maximum `row_limit` (`TABLE_MAX_OUTPUT_ROWS`). */
export const TABLE_ROW_LIMIT_MAX = 1000;

/** Default serialized output cap. */
export const TABLE_OUTPUT_BYTE_LIMIT_DEFAULT = 65_536;

const COLUMN_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

/**
 * Clamp analyze row_limit to 1–1000.
 *
 * @param value - Raw input.
 * @returns Integer in range, default 100.
 */
export function clampTableRowLimit(value: number): number {
  if (!Number.isFinite(value)) {
    return TABLE_ROW_LIMIT_DEFAULT;
  }
  return Math.min(TABLE_ROW_LIMIT_MAX, Math.max(1, Math.floor(value)));
}

/**
 * Return whether a column id is a safe internal identifier.
 *
 * @param value - Candidate id.
 * @returns True when it matches the plan regex.
 */
export function isInternalColumnId(value: string): boolean {
  return COLUMN_RE.test(value) && value.length <= 64;
}

/**
 * Build a `TableQueryPlan` with only allow-listed fields.
 *
 * Extra keys such as `sql` are omitted even if the caller passes them.
 *
 * @param input - Partial plan from the UI.
 * @returns Plan object for `{ plan }` POST body.
 */
export function buildTableQueryPlan(
  input: TableQueryPlan & { sql?: unknown },
): TableQueryPlan {
  const predicates = (input.predicates ?? []).filter((item) =>
    TABLE_PREDICATE_OPERATORS.includes(item.operator),
  );
  const aggregations = (input.aggregations ?? []).filter((item) =>
    TABLE_AGGREGATION_OPS.includes(item.op),
  );
  const orderBy = (input.order_by ?? []).filter((item) =>
    TABLE_SORT_DIRECTIONS.includes(item.direction),
  );
  const plan: TableQueryPlan = {
    table_id: input.table_id,
    version_id: input.version_id,
    columns: (input.columns ?? []).filter(isInternalColumnId),
    predicates,
    aggregations,
    group_by: (input.group_by ?? []).filter(isInternalColumnId),
    order_by: orderBy,
    comparison: input.comparison ?? null,
    units: input.units ?? null,
    row_limit: clampTableRowLimit(input.row_limit ?? TABLE_ROW_LIMIT_DEFAULT),
    output_byte_limit: input.output_byte_limit ?? TABLE_OUTPUT_BYTE_LIMIT_DEFAULT,
  };
  return plan;
}

/**
 * Wrap a plan for `POST /tables/analyze`. Extra root fields are omitted.
 *
 * @param plan - Validated plan.
 * @returns `{ plan }` only.
 */
export function tableAnalyzeBody(
  plan: TableQueryPlan & { sql?: unknown },
): { plan: TableQueryPlan } {
  return { plan: buildTableQueryPlan(plan) };
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
 * `/tables` with no chat disclosure must not show export.
 *
 * @param toolKeys - `optional_tool_disclosure.tool_keys` from the current run.
 * @returns True only for catalog export keys.
 */
export function tableExportAllowed(toolKeys: readonly string[]): boolean {
  const exportKeys = new Set(["export_csv", "export_xlsx", "export_parquet"]);
  return toolKeys.some((key) => exportKeys.has(key));
}

export {
  TABLE_AGGREGATION_OPS,
  TABLE_PREDICATE_OPERATORS,
  TABLE_SORT_DIRECTIONS,
} from "./types";
export type {
  TableAggregationOp,
  TablePredicate,
  TablePredicateOperator,
  TableSortDirection,
};
