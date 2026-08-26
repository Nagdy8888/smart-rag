/**
 * Citation, feedback, and cancel HTTP helpers.
 */

import type { CitationResponse, FeedbackResponse, FeedbackTag, RunResponse } from "../types";
import {
  ClassifiedApiError,
  classifiedOrGenericFailure,
  throwIfNotOk,
} from "./errors";
import type { ApiAuth } from "./headers";
import { paidMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";
import { parseFeedbackResponse, parseRunResponse } from "./parsers";

const CITATION_SNIPPET_KEYS = /^(snippet|passage|text|html|content|body)$/i;

/**
 * Keep citation ids and coordinate provenance. Drop passage/snippet fields.
 *
 * @param item - One JSON citation object.
 * @returns Typed citation, or null when `citation_id` is missing.
 */
function parseCitationItem(item: unknown): CitationResponse | null {
  if (item === null || typeof item !== "object" || Array.isArray(item)) {
    return null;
  }
  const row = item as Record<string, unknown>;
  const citationId = row.citation_id;
  if (typeof citationId !== "string" || citationId.trim() === "") {
    return null;
  }
  const provenanceRaw = row.provenance;
  const provenance: Record<string, unknown> = {};
  if (
    provenanceRaw !== null &&
    typeof provenanceRaw === "object" &&
    !Array.isArray(provenanceRaw)
  ) {
    for (const [key, value] of Object.entries(
      provenanceRaw as Record<string, unknown>,
    )) {
      if (CITATION_SNIPPET_KEYS.test(key)) {
        continue;
      }
      provenance[key] = value;
    }
  }
  return {
    citation_id: citationId,
    citation_index: Number(row.citation_index ?? 0),
    chunk_id:
      row.chunk_id === null || row.chunk_id === undefined
        ? null
        : String(row.chunk_id),
    provenance,
    source_unavailable: Boolean(row.source_unavailable),
  };
}

/**
 * Fetch citations for an owned run.
 *
 * @param auth - Access token.
 * @param runId - Run UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Citation identifiers. No passage text.
 */
export async function listCitations(
  auth: ApiAuth,
  runId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<CitationResponse[]> {
  const response = await fetchImpl(apiUrl(`/runs/${runId}/citations`), {
    headers: resumeHeaders(auth),
  });
  if (response.status === 404) {
    return [];
  }
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed
    .map(parseCitationItem)
    .filter((item): item is CitationResponse => item !== null);
}

/**
 * Submit thumbs feedback with a required unmerged tag.
 *
 * @param auth - Access token.
 * @param runId - Run UUID.
 * @param thumbsUp - Rating 5 when true.
 * @param tag - Exact catalog tag.
 * @param comment - Optional correction text.
 * @param fetchImpl - Injected fetch.
 * @returns True on success.
 */
export async function submitFeedback(
  auth: ApiAuth,
  runId: string,
  thumbsUp: boolean,
  tag: FeedbackTag,
  comment: string | null,
  fetchImpl: typeof fetch = fetch,
): Promise<FeedbackResponse> {
  const response = await fetchImpl(apiUrl(`/runs/${runId}/feedback`), {
    method: "POST",
    headers: paidMutationHeaders(auth),
    body: JSON.stringify({
      thumbs_up: thumbsUp,
      tag,
      comment,
    }),
  });
  const body = await readJsonObject(response);
  if (response.status !== 201) {
    throw new ClassifiedApiError(
      classifiedOrGenericFailure(response.status, body, response.headers),
    );
  }
  return parseFeedbackResponse(body);
}

/**
 * Cancel a pending or running owned run.
 *
 * @param auth - Access token.
 * @param runId - Run UUID.
 * @param fetchImpl - Injected fetch.
 * @returns True on success.
 */
export async function cancelRun(
  auth: ApiAuth,
  runId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<RunResponse> {
  const response = await fetchImpl(apiUrl(`/runs/${runId}/cancel`), {
    method: "POST",
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  throwIfNotOk(response, body);
  return parseRunResponse(body);
}
