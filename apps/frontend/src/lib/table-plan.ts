/**
 * Extra-forbid TableQueryPlan builder. No SQL field. No client-side totals.
 * `/tables` never renders Export; there is no standalone export contract.
 */

import {
  TABLE_AGGREGATION_OPS,
  TABLE_PREDICATE_OPERATORS,
  TABLE_SORT_DIRECTIONS,
  type TableAggregationOp,
  type TableManifestResponse,
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

const SQL_OR_PATH_TOKENS = [
  "select ",
  " attach",
  "../",
  "://",
  "pragma",
  "copy ",
  ";",
] as const;

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
export type TablePlanCompileReason =
  | "incomplete"
  | "unknown_column"
  | "sql";

/**
 * Compile result for Analyze.
 */
export type TablePlanCompileResult =
  | { ok: true; plan: TableQueryPlan }
  | { ok: false; reason: TablePlanCompileReason };

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
 * Return whether a string looks like SQL, a path, or a URL.
 *
 * @param value - Untrusted scalar.
 * @returns True when the value must not be posted.
 */
export function looksLikeSqlOrPath(value: string): boolean {
  const lowered = value.toLowerCase();
  return SQL_OR_PATH_TOKENS.some((token) => lowered.includes(token));
}

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

/**
 * Preselect only a manifest the caller can actually list.
 *
 * An explicit `tableId` that is not in `manifests` stays unselected even when
 * `documentId` matches another row.
 *
 * @param manifests - Authorized `GET /tables` rows.
 * @param userSelectedId - Sidebar/select click, or null to follow the URL.
 * @param tableIdParam - `?tableId=` from the URL.
 * @param documentIdParam - `?documentId=` from the URL.
 * @returns Accessible manifest, or null.
 */
export function resolveSelectedManifest(
  manifests: readonly TableManifestResponse[],
  userSelectedId: string | null,
  tableIdParam: string | null,
  documentIdParam: string | null,
): TableManifestResponse | null {
  if (userSelectedId !== null && userSelectedId !== "") {
    return manifests.find((item) => item.table_id === userSelectedId) ?? null;
  }
  if (tableIdParam !== null && tableIdParam !== "") {
    return manifests.find((item) => item.table_id === tableIdParam) ?? null;
  }
  if (documentIdParam !== null && documentIdParam !== "") {
    return (
      manifests.find((item) => item.document_id === documentIdParam) ?? null
    );
  }
  return null;
}

/**
 * Parse a predicate value. `in` uses a comma-separated list.
 *
 * @param raw - Form text.
 * @param operator - Allow-listed operator.
 * @returns Scalar or list suitable for `TablePredicate.value`.
 */
export function parsePredicateValue(
  raw: string,
  operator: TablePredicateOperator,
): TablePredicate["value"] {
  if (operator === "in") {
    return raw.split(",").map((part) => parsePredicateScalar(part.trim()));
  }
  return parsePredicateScalar(raw);
}

/**
 * Parse one predicate scalar.
 *
 * @param raw - Form text.
 * @returns JSON scalar.
 */
function parsePredicateScalar(
  raw: string,
): string | number | boolean | null {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return null;
  }
  if (trimmed === "true") {
    return true;
  }
  if (trimmed === "false") {
    return false;
  }
  if (/^-?\d+(?:\.\d+)?$/.test(trimmed)) {
    return Number(trimmed);
  }
  return trimmed;
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
 * Compile a guided draft. Unknown columns, operators, and SQL-shaped values
 * fail closed before fetch.
 *
 * @param selected - Accessible manifest.
 * @param draft - Builder state.
 * @returns Plan, or a reason that must not be posted.
 */
export function compileTablePlanDraft(
  selected: TableManifestResponse,
  draft: TablePlanDraft,
): TablePlanCompileResult {
  const columnBag: string[] = [
    ...draft.columns,
    ...draft.filters.map((item) => item.column),
    ...draft.aggregations.flatMap((item) =>
      item.op === "count" && item.column.trim() === "" ? [] : [item.column],
    ),
    ...draft.groupBy,
    ...draft.sorts.map((item) => item.column),
  ];
  if (draft.comparison !== null) {
    columnBag.push(draft.comparison.column);
    columnBag.push(...draft.comparison.left.map((item) => item.column));
    columnBag.push(...draft.comparison.right.map((item) => item.column));
  }

  const valueBag: string[] = [
    ...draft.filters.map((item) => item.value),
    ...(draft.comparison === null
      ? []
      : [
          ...draft.comparison.left.map((item) => item.value),
          ...draft.comparison.right.map((item) => item.value),
        ]),
  ];

  if (valueBag.some((item) => looksLikeSqlOrPath(item))) {
    return { ok: false, reason: "sql" };
  }
  if (columnBag.some((item) => looksLikeSqlOrPath(item))) {
    return { ok: false, reason: "sql" };
  }
  if (columnBag.some((item) => !isInternalColumnId(item.trim()))) {
    return { ok: false, reason: "unknown_column" };
  }
  if (
    draft.filters.some(
      (item) => !TABLE_PREDICATE_OPERATORS.includes(item.operator),
    ) ||
    draft.aggregations.some(
      (item) => !TABLE_AGGREGATION_OPS.includes(item.op),
    ) ||
    draft.sorts.some(
      (item) => !TABLE_SORT_DIRECTIONS.includes(item.direction),
    ) ||
    (draft.comparison !== null &&
      !TABLE_AGGREGATION_OPS.includes(draft.comparison.aggregation))
  ) {
    return { ok: false, reason: "unknown_column" };
  }

  const predicates = draft.filters.map((item) => ({
    column: item.column.trim(),
    operator: item.operator,
    value: parsePredicateValue(item.value, item.operator),
  }));
  const aggregations = draft.aggregations.map((item, index) => ({
    op: item.op,
    column:
      item.op === "count" && item.column.trim() === ""
        ? null
        : item.column.trim(),
    alias: isInternalColumnId(item.alias.trim())
      ? item.alias.trim()
      : `agg_${index}`,
  }));
  const comparison =
    draft.comparison === null
      ? null
      : {
          aggregation: draft.comparison.aggregation,
          column: draft.comparison.column.trim(),
          left: draft.comparison.left.map((item) => ({
            column: item.column.trim(),
            operator: item.operator,
            value: parsePredicateValue(item.value, item.operator),
          })),
          right: draft.comparison.right.map((item) => ({
            column: item.column.trim(),
            operator: item.operator,
            value: parsePredicateValue(item.value, item.operator),
          })),
        };

  const hasOperation =
    predicates.length > 0 ||
    aggregations.length > 0 ||
    draft.groupBy.length > 0 ||
    draft.sorts.length > 0 ||
    comparison !== null;
  if (!hasOperation) {
    return { ok: false, reason: "incomplete" };
  }

  return {
    ok: true,
    plan: buildTableQueryPlan({
      table_id: selected.table_id,
      version_id: selected.version_id,
      columns: draft.columns.map((item) => item.trim()),
      predicates,
      aggregations,
      group_by: draft.groupBy.map((item) => item.trim()),
      order_by: draft.sorts.map((item) => ({
        column: item.column.trim(),
        direction: item.direction,
      })),
      comparison,
    }),
  };
}

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
