/**
 * Compile guided drafts into extra-forbid TableQueryPlan POST bodies.
 */

import {
  TABLE_AGGREGATION_OPS,
  TABLE_PREDICATE_OPERATORS,
  TABLE_SORT_DIRECTIONS,
  type TableManifestResponse,
  type TableQueryPlan,
} from "../types";
import {
  TABLE_OUTPUT_BYTE_LIMIT_DEFAULT,
  TABLE_ROW_LIMIT_DEFAULT,
  type TablePlanDraft,
  type TablePlanCompileResult,
} from "./draft";
import {
  clampTableRowLimit,
  isInternalColumnId,
  looksLikeSqlOrPath,
  parsePredicateValue,
} from "./validate";

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
 * Restrict manifests to one document when the URL seeds `documentId`.
 *
 * @param manifests - Authorized `GET /tables` rows.
 * @param documentId - `?documentId=`, or null for the full list.
 * @returns The same rows, or only those whose `document_id` matches.
 */
export function manifestsForDocument(
  manifests: readonly TableManifestResponse[],
  documentId: string | null,
): readonly TableManifestResponse[] {
  if (documentId === null || documentId === "") {
    return manifests;
  }
  return manifests.filter((item) => item.document_id === documentId);
}

/**
 * Collect unique document ids that need a title lookup.
 *
 * Order is first appearance in `manifests`, then a seeded id that has no
 * extracted tables.
 *
 * @param manifests - Authorized `GET /tables` rows.
 * @param seededDocumentId - `?documentId=` from the URL.
 * @returns Distinct ids for `GET /documents/{id}`.
 */
export function tableDocumentIds(
  manifests: readonly TableManifestResponse[],
  seededDocumentId: string | null,
): readonly string[] {
  const ids: string[] = [];
  const seen = new Set<string>();
  for (const item of manifests) {
    if (seen.has(item.document_id)) {
      continue;
    }
    seen.add(item.document_id);
    ids.push(item.document_id);
  }
  if (
    seededDocumentId !== null &&
    seededDocumentId !== "" &&
    !seen.has(seededDocumentId)
  ) {
    ids.push(seededDocumentId);
  }
  return ids;
}

/**
 * Prefer a document title from `GET /documents/{id}`; otherwise the id.
 *
 * @param documents - Successful document fetches.
 * @param documentId - Manifest or seed id.
 * @returns Title, or `document_id` when the title is null or the fetch missed.
 */
export function documentDisplayName(
  documents: readonly { document_id: string; title: string | null }[],
  documentId: string,
): string {
  const match = documents.find((item) => item.document_id === documentId);
  if (match === undefined) {
    return documentId;
  }
  return match.title ?? match.document_id;
}

/**
 * Build `/tables` with optional table and document query params.
 *
 * @param options - Ids to include. Empty strings are omitted.
 * @returns Path, or path with a query string.
 */
export function tablesWorkspaceHref(options: {
  tableId?: string | null;
  documentId?: string | null;
}): string {
  const params = new URLSearchParams();
  if (options.tableId !== undefined && options.tableId !== null && options.tableId !== "") {
    params.set("tableId", options.tableId);
  }
  if (
    options.documentId !== undefined &&
    options.documentId !== null &&
    options.documentId !== ""
  ) {
    params.set("documentId", options.documentId);
  }
  const query = params.toString();
  return query === "" ? "/tables" : `/tables?${query}`;
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
