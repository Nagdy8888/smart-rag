/**
 * Guided TableQueryPlan draft types and user-safe copy.
 */

import type {
  TableAggregationOp,
  TablePredicateOperator,
  TableSortDirection,
} from "../types";

/** Default `row_limit` from the schema. */
export const TABLE_ROW_LIMIT_DEFAULT = 100;

/** Maximum `row_limit` (`TABLE_MAX_OUTPUT_ROWS`). */
export const TABLE_ROW_LIMIT_MAX = 1000;

/** Default serialized output cap. */
export const TABLE_OUTPUT_BYTE_LIMIT_DEFAULT = 65_536;

/** Ordinary lookup is Hybrid; Analyze requires a guided operation. */
export const PLAN_INCOMPLETE_COPY =
  "Add a filter, aggregation, group, sort, or comparison. Ordinary lookup stays Hybrid.";

/** Client-side allow-list rejection before `POST /tables/analyze`. */
export const UNKNOWN_COLUMN_COPY =
  "Unknown columns and operators are rejected before submission.";

/** Raw SQL is never a plan field. */
export const SQL_REJECTED_COPY = "Raw SQL is not accepted.";

/** Empty successful analyze. */
export const EMPTY_ANALYZE_ROWS_COPY = "The analysis returned no rows.";

/** Empty `GET /tables` list. */
export const EMPTY_MANIFESTS_COPY = "No structured tables are available.";

/** Result keys that fail the internal identifier regex are omitted. */
export const OMITTED_RESULT_COLUMN_COPY =
  "A result column was omitted because it is not an internal identifier.";

/** Client-only sort control. Does not mutate the submitted plan. */
export const DISPLAY_SORT_LABEL =
  "Display sort (does not change the submitted plan)";

/**
 * One predicate row in the guided builder.
 */
export type TablePredicateDraft = {
  column: string;
  operator: TablePredicateOperator;
  value: string;
};

/**
 * One aggregation row in the guided builder.
 */
export type TableAggregationDraft = {
  op: TableAggregationOp;
  column: string;
  alias: string;
};

/**
 * One order-by row in the guided builder.
 */
export type TableSortDraft = {
  column: string;
  direction: TableSortDirection;
};

/**
 * Optional two-sided comparison in the guided builder.
 */
export type TableComparisonDraft = {
  aggregation: TableAggregationOp;
  column: string;
  left: TablePredicateDraft[];
  right: TablePredicateDraft[];
};

/**
 * Guided plan draft. Extra SQL keys are never stored.
 */
export type TablePlanDraft = {
  columns: string[];
  filters: TablePredicateDraft[];
  aggregations: TableAggregationDraft[];
  groupBy: string[];
  sorts: TableSortDraft[];
  comparison: TableComparisonDraft | null;
};

/** Collapsed optional sections. */
export const EMPTY_TABLE_PLAN_DRAFT: TablePlanDraft = {
  columns: [],
  filters: [],
  aggregations: [],
  groupBy: [],
  sorts: [],
  comparison: null,
};

/**
 * Why a guided draft cannot be posted.
 */
export type TablePlanCompileReason = "incomplete" | "unknown_column" | "sql";

/**
 * Compile result for Analyze.
 */
export type TablePlanCompileResult =
  | { ok: true; plan: import("../types").TableQueryPlan }
  | { ok: false; reason: TablePlanCompileReason };

/**
 * English banner for a compile failure.
 *
 * @param reason - Compile reason.
 * @returns Status copy.
 */
export function tablePlanCompileCopy(reason: TablePlanCompileReason): string {
  if (reason === "incomplete") {
    return PLAN_INCOMPLETE_COPY;
  }
  if (reason === "sql") {
    return SQL_REJECTED_COPY;
  }
  return UNKNOWN_COLUMN_COPY;
}
