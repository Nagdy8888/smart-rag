/**
 * Table manifest and analyze HTTP helpers.
 */

import type { TableAnalyzeResponse, TableManifestResponse, TableQueryPlan } from "../types";
import { tableAnalyzeBody } from "../table-plan";
import { ClassifiedApiError, sanitizedDetail, throwIfNotOk } from "./errors";
import type { ApiAuth } from "./headers";
import { paidMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";

/**
 * List authorized table manifests. No storage paths.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Manifests.
 * @throws ClassifiedApiError on 401/403/429/5xx.
 */
export async function listTables(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<TableManifestResponse[]> {
  const response = await fetchImpl(apiUrl("/tables"), {
    headers: resumeHeaders(auth),
  });
  const parsed: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const body =
      parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
        ? (parsed as Record<string, unknown>)
        : {};
    throwIfNotOk(response, body);
  }
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed.map((item) => {
    const row = item as Record<string, unknown>;
    return {
      table_id: String(row.table_id ?? ""),
      document_id: String(row.document_id ?? ""),
      version_id: String(row.version_id ?? ""),
      table_name: String(row.table_name ?? ""),
      sheet_name: typeof row.sheet_name === "string" ? row.sheet_name : null,
      row_count: typeof row.row_count === "number" ? row.row_count : null,
      column_count: typeof row.column_count === "number" ? row.column_count : null,
    };
  });
}

/**
 * Execute one extra-forbid TableQueryPlan. Extra SQL-like fields are omitted.
 *
 * @param auth - Access token.
 * @param plan - Declarative plan.
 * @param fetchImpl - Injected fetch.
 * @returns Deterministic rows and source_ranges.
 * @throws ClassifiedApiError on 400/401/403/404/422/429/5xx.
 */
export async function analyzeTable(
  auth: ApiAuth,
  plan: TableQueryPlan,
  fetchImpl: typeof fetch = fetch,
): Promise<TableAnalyzeResponse> {
  const response = await fetchImpl(apiUrl("/tables/analyze"), {
    method: "POST",
    headers: paidMutationHeaders(auth),
    body: JSON.stringify(tableAnalyzeBody(plan)),
  });
  const parsed = await readJsonObject(response);
  if (response.status === 400) {
    throw new ClassifiedApiError({
      kind: "validation",
      detail: sanitizedDetail(parsed, "table_plan_rejected"),
    });
  }
  throwIfNotOk(response, parsed);
  const rowsRaw = Array.isArray(parsed.rows) ? parsed.rows : [];
  const rangesRaw = Array.isArray(parsed.source_ranges)
    ? parsed.source_ranges
    : [];
  return {
    table_id: String(parsed.table_id ?? ""),
    version_id: String(parsed.version_id ?? ""),
    document_id: String(parsed.document_id ?? ""),
    rows: rowsRaw.filter(
      (row): row is Record<string, unknown> =>
        row !== null && typeof row === "object" && !Array.isArray(row),
    ),
    source_ranges: rangesRaw.map(String),
  };
}
