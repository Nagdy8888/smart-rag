/**
 * Graph search and inspect HTTP helpers.
 */

import type { GraphEntityResponse, GraphInspectRequest, GraphInspectResponse } from "../types";
import { buildGraphInspectRequest, clampGraphSearchLimit } from "../graph-client";
import { ClassifiedApiError, sanitizedDetail, throwIfNotOk } from "./errors";
import type { ApiAuth } from "./headers";
import { paidMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";

/**
 * Search authorized graph entities. Limit is clamped to 25.
 *
 * @param auth - Access token.
 * @param query - Bounded search string.
 * @param limit - Requested limit.
 * @param fetchImpl - Injected fetch.
 * @returns Hits without vendor prose.
 */
export async function searchGraphEntities(
  auth: ApiAuth,
  query: string,
  limit: number = 25,
  fetchImpl: typeof fetch = fetch,
): Promise<GraphEntityResponse[]> {
  const capped = clampGraphSearchLimit(limit);
  const url = apiUrl(
    `/graph/entities/search?q=${encodeURIComponent(query)}&limit=${String(capped)}`,
  );
  const response = await fetchImpl(url, { headers: resumeHeaders(auth) });
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
      object_id: String(row.object_id ?? ""),
      object_type: String(row.object_type ?? ""),
      chunk_id: String(row.chunk_id ?? ""),
      document_id: String(row.document_id ?? ""),
      version_id: String(row.version_id ?? ""),
      support: Number(row.support ?? 0),
    };
  });
}

/**
 * Inspect authorized graph objects. Depth is clamped to 1–3 on this client.
 *
 * Extra title fields on nodes are ignored.
 *
 * @param auth - Access token.
 * @param request - Seed keys and/or document id.
 * @param fetchImpl - Injected fetch.
 * @returns Inspect payload.
 */
export async function inspectGraph(
  auth: ApiAuth,
  request: GraphInspectRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<GraphInspectResponse> {
  const body = buildGraphInspectRequest(
    request.entity_keys,
    request.document_id ?? null,
    request.depth,
  );
  const payload: {
    entity_keys: string[];
    depth: number;
    document_id?: string;
  } = {
    entity_keys: body.entity_keys,
    depth: body.depth,
  };
  if (body.document_id) {
    payload.document_id = body.document_id;
  }
  const response = await fetchImpl(apiUrl("/graph/inspect"), {
    method: "POST",
    headers: paidMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const parsed = await readJsonObject(response);
  if (response.status === 400) {
    throw new ClassifiedApiError({
      kind: "validation",
      detail: sanitizedDetail(parsed, "inspect_rejected"),
    });
  }
  throwIfNotOk(response, parsed);
  const nodesRaw = Array.isArray(parsed.nodes) ? parsed.nodes : [];
  const locatorsRaw = Array.isArray(parsed.locators) ? parsed.locators : [];
  const limitationsRaw = Array.isArray(parsed.limitations)
    ? parsed.limitations
    : [];
  return {
    nodes: nodesRaw.map((item) => {
      const row = item as Record<string, unknown>;
      return {
        object_type: String(row.object_type ?? ""),
        object_id: String(row.object_id ?? ""),
        chunk_id: String(row.chunk_id ?? ""),
        document_id: String(row.document_id ?? ""),
        version_id: String(row.version_id ?? ""),
        support: Number(row.support ?? 0),
        hop: Number(row.hop ?? 0),
      };
    }),
    locators: locatorsRaw.map((item) => {
      const row = item as Record<string, unknown>;
      const section = row.section_path;
      return {
        chunk_id: String(row.chunk_id ?? ""),
        document_id: String(row.document_id ?? ""),
        version_id: String(row.version_id ?? ""),
        page_number: typeof row.page_number === "number" ? row.page_number : null,
        section_path: Array.isArray(section) ? section.map(String) : [],
        sheet_name: typeof row.sheet_name === "string" ? row.sheet_name : null,
        range_ref: typeof row.range_ref === "string" ? row.range_ref : null,
        source_url: typeof row.source_url === "string" ? row.source_url : null,
      };
    }),
    limitations: limitationsRaw.map((item) => {
      const row = item as Record<string, unknown>;
      return {
        code: String(row.code ?? ""),
        count: typeof row.count === "number" ? row.count : null,
      };
    }),
    row_count: Number(parsed.row_count ?? 0),
    depth: Number(parsed.depth ?? body.depth),
  };
}
