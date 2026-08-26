/**
 * Deterministic table-plan OpenAPI types.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

/** Allow-listed table predicate operators. */
export const TABLE_PREDICATE_OPERATORS = [
  "eq",
  "ne",
  "lt",
  "le",
  "gt",
  "ge",
  "in",
] as const;

export type TablePredicateOperator = (typeof TABLE_PREDICATE_OPERATORS)[number];

/** Allow-listed aggregations. */
export const TABLE_AGGREGATION_OPS = [
  "sum",
  "count",
  "average",
  "min",
  "max",
] as const;

export type TableAggregationOp = (typeof TABLE_AGGREGATION_OPS)[number];

/** Allow-listed sort directions. */
export const TABLE_SORT_DIRECTIONS = ["asc", "desc"] as const;

export type TableSortDirection = (typeof TABLE_SORT_DIRECTIONS)[number];

/** One typed predicate. Extra SQL/path fields are forbidden. */
export type TablePredicate = {
  column: string;
  operator: TablePredicateOperator;
  value: string | number | boolean | null | Array<string | number | boolean | null>;
};

/** One aggregation. COUNT may omit `column`. */
export type TableAggregation = {
  op: TableAggregationOp;
  column?: string | null;
  alias: string;
};

/** One order-by clause. */
export type TableOrder = {
  column: string;
  direction: TableSortDirection;
};

/**
 * Declarative table plan. Matches `TableQueryPlan` extra=forbid.
 * There is no SQL field.
 */
export type TableQueryPlan = {
  table_id: string;
  version_id: string;
  columns?: string[];
  predicates?: TablePredicate[];
  aggregations?: TableAggregation[];
  group_by?: string[];
  order_by?: TableOrder[];
  comparison?: {
    aggregation: TableAggregationOp;
    column: string;
    left: TablePredicate[];
    right: TablePredicate[];
  } | null;
  units?: string | null;
  row_limit?: number;
  output_byte_limit?: number;
};

/** `GET /tables` manifest. No storage paths. */
export type TableManifestResponse = {
  table_id: string;
  document_id: string;
  version_id: string;
  table_name: string;
  sheet_name: string | null;
  row_count: number | null;
  column_count: number | null;
};

/** `POST /tables/analyze` deterministic result. */
export type TableAnalyzeResponse = {
  table_id: string;
  version_id: string;
  document_id: string;
  rows: Array<Record<string, unknown>>;
  source_ranges: string[];
};
