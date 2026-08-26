/**
 * Extra-forbid TableQueryPlan barrel. No SQL field. No client-side totals.
 * `/tables` never renders Export; there is no standalone export contract.
 */

export {
  DISPLAY_SORT_LABEL,
  EMPTY_ANALYZE_ROWS_COPY,
  EMPTY_MANIFESTS_COPY,
  EMPTY_TABLE_PLAN_DRAFT,
  OMITTED_RESULT_COLUMN_COPY,
  PLAN_INCOMPLETE_COPY,
  SQL_REJECTED_COPY,
  TABLE_OUTPUT_BYTE_LIMIT_DEFAULT,
  TABLE_ROW_LIMIT_DEFAULT,
  TABLE_ROW_LIMIT_MAX,
  UNKNOWN_COLUMN_COPY,
  tablePlanCompileCopy,
} from "./table-plan/draft";
export type {
  TableAggregationDraft,
  TableComparisonDraft,
  TablePlanCompileReason,
  TablePlanCompileResult,
  TablePlanDraft,
  TablePredicateDraft,
  TableSortDraft,
} from "./table-plan/draft";
export {
  clampTableRowLimit,
  isInternalColumnId,
  looksLikeSqlOrPath,
  parsePredicateValue,
} from "./table-plan/validate";
export {
  buildTableQueryPlan,
  compileTablePlanDraft,
  resolveSelectedManifest,
  tableAnalyzeBody,
} from "./table-plan/compile";
export {
  allowListedResultColumns,
  clientComputedTableTotal,
  isNumericTableCell,
  tableExportAllowed,
} from "./table-plan/results";
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
} from "./types";
