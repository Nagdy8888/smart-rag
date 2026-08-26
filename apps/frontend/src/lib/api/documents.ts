/**
 * Document list, status, and delete HTTP helpers.
 */

import type {
  DocumentIngestionStatusResponse,
  DocumentResponse,
  IngestionJobSummary,
  IngestionStatusVersion,
} from "../types";
import { throwIfNotOk } from "./errors";
import { DOCUMENT_LIST_PAGE_SIZE } from "./documents-constants";
import type { ApiAuth } from "./headers";
import { paidMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";
import { parseDocumentResponse } from "./parsers";

export { DOCUMENT_LIST_PAGE_SIZE } from "./documents-constants";
export { nextDocumentCursor, parseDocumentResponse } from "./parsers";

/**
 * List ACL-visible documents with bounded `created_at,id` keyset pagination.
 *
 * Continuation is inferred from page length. This client never invents
 * `next_cursor`.
 *
 * @param auth - Access token.
 * @param options - Optional keyset cursor and page size.
 * @param fetchImpl - Injected fetch.
 * @returns One page of documents, newest first.
 */
export async function listDocuments(
  auth: ApiAuth,
  options: { cursor?: string | null; limit?: number } = {},
  fetchImpl: typeof fetch = fetch,
): Promise<DocumentResponse[]> {
  const limit = options.limit ?? DOCUMENT_LIST_PAGE_SIZE;
  const params = new URLSearchParams({ limit: String(limit) });
  if (options.cursor) {
    params.set("cursor", options.cursor);
  }
  const response = await fetchImpl(apiUrl(`/documents?${params.toString()}`), {
    headers: resumeHeaders(auth),
  });
  if (!response.ok) {
    const failureBody = await readJsonObject(response);
    throwIfNotOk(response, failureBody);
  }
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed
    .filter((row): row is Record<string, unknown> => row !== null && typeof row === "object")
    .map(parseDocumentResponse);
}

/**
 * Fetch Hybrid/BM25/graph-handoff diagnostics for one version.
 *
 * Graph ready is never inferred from upload alone.
 *
 * @param auth - Access token.
 * @param versionId - Document version UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Envelope, or null on 404. 404 bodies are not parsed for titles.
 */
export async function fetchVersionStatus(
  auth: ApiAuth,
  versionId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<DocumentIngestionStatusResponse | null> {
  const response = await fetchImpl(
    apiUrl(`/ingestion/versions/${versionId}/status`),
    { headers: resumeHeaders(auth) },
  );
  if (response.status === 404) {
    return null;
  }
  const body = (await response.json()) as {
    version?: IngestionStatusVersion;
    recent_jobs?: IngestionJobSummary[];
  };
  const version = body.version;
  if (version === undefined) {
    return null;
  }
  if (version.bm25 === undefined) {
    version.bm25 = {
      active_index_version: null,
      index_schema_version: null,
      lag_seconds: null,
      pending: 0,
      processing: 0,
      failed: 0,
      dead_letter: 0,
      retry_attempts: 0,
      verified_at: null,
    };
  }
  if (version.graph_handoff === undefined) {
    version.graph_handoff = {
      pending: 0,
      processing: 0,
      completed: 0,
      failed: 0,
      dead_letter: 0,
    };
  }
  return {
    version,
    recent_jobs: Array.isArray(body.recent_jobs) ? body.recent_jobs : [],
  };
}

export type DocumentFetchResult =
  | { ok: true; document: DocumentResponse }
  | { ok: false; notFound: true };

/**
 * GET `/documents/{document_id}`. 404 must not leak a title.
 *
 * @param auth - Access token.
 * @param documentId - Document UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Document or `{ notFound: true }` without parsing error titles.
 */
export async function fetchDocument(
  auth: ApiAuth,
  documentId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<DocumentFetchResult> {
  const response = await fetchImpl(apiUrl(`/documents/${documentId}`), {
    headers: resumeHeaders(auth),
  });
  if (response.status === 404) {
    await response.arrayBuffer().catch(() => undefined);
    return { ok: false, notFound: true };
  }
  if (!response.ok) {
    await response.arrayBuffer().catch(() => undefined);
    return { ok: false, notFound: true };
  }
  const body = await readJsonObject(response);
  return {
    ok: true,
    document: parseDocumentResponse(body),
  };
}

/**
 * DELETE `/documents/{document_id}`. Owner/admin only. 204 is success.
 *
 * @param auth - Access token.
 * @param documentId - Document UUID.
 * @param fetchImpl - Injected fetch.
 * @throws ClassifiedApiError on 403/404/429/5xx.
 */
export async function deleteDocument(
  auth: ApiAuth,
  documentId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const response = await fetchImpl(apiUrl(`/documents/${documentId}`), {
    method: "DELETE",
    headers: paidMutationHeaders(auth),
  });
  if (response.status === 204) {
    return;
  }
  const body = await readJsonObject(response);
  throwIfNotOk(response, body);
}
