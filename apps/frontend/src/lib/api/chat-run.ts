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

const CITATION_SNIPPET_KEYS =
  /^(snippet|passage|text|html|content|body|excerpt|span|quote|evidence_excerpt|passage_text)$/i;

/**
 * Keep citation ids, typed PDF fields, and locator provenance.
 *
 * Drops passage/snippet keys from provenance. Reads `evidence_excerpt` only
 * from the top-level field so nested copies cannot leak into chips.
 *
 * @param item - One JSON citation object.
 * @returns Typed citation, or null when `citation_id` is missing.
 */
export function parseCitationItem(item: unknown): CitationResponse | null {
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
  const sourceUrl = parseHttpsSourceUrl(row.source_url);
  return {
    citation_id: citationId,
    citation_index: Number(row.citation_index ?? 0),
    chunk_id:
      row.chunk_id === null || row.chunk_id === undefined
        ? null
        : String(row.chunk_id),
    provenance,
    source_unavailable: Boolean(row.source_unavailable),
    source_kind: parseSourceKind(row.source_kind),
    web_source_id: parseOptionalString(row.web_source_id),
    paragraph_index: parseParagraphIndex(row.paragraph_index),
    document_title: parseOptionalString(row.document_title),
    pdf_page_number: parsePdfPageNumber(row.pdf_page_number),
    evidence_excerpt: parseEvidenceExcerpt(row.evidence_excerpt),
    ...(sourceUrl === null ? {} : { source_url: sourceUrl }),
  };
}

/**
 * Parse a fragment-free HTTPS locator from citation detail.
 *
 * http, userinfo, and fragment values are dropped. Company rows omit this.
 *
 * @param value - Raw `source_url`.
 * @returns Canonical HTTPS URL, or null.
 */
export function parseHttpsSourceUrl(value: unknown): string | null {
  if (typeof value !== "string" || value === "") {
    return null;
  }
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "https:") {
      return null;
    }
    if (parsed.username !== "" || parsed.password !== "") {
      return null;
    }
    if (parsed.hash !== "") {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

/**
 * Parse catalog source kind. Missing values are company documents.
 *
 * @param value - Raw `source_kind`.
 * @returns Non-empty kind string.
 */
function parseSourceKind(value: unknown): string {
  if (typeof value === "string" && value.trim() !== "") {
    return value;
  }
  return "company_document";
}

/**
 * Parse a nullable string field.
 *
 * @param value - Raw JSON value.
 * @returns Null when missing, non-string, or empty.
 */
function parseOptionalString(value: unknown): string | null {
  if (typeof value !== "string" || value === "") {
    return null;
  }
  return value;
}

/**
 * Parse a paragraph mapping. Invalid or out-of-range values become null.
 *
 * @param value - Raw `paragraph_index`.
 * @returns Integer 0–5, or null.
 */
function parseParagraphIndex(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 5) {
    return value;
  }
  if (typeof value === "string" && /^(0|[1-9]\d*)$/.test(value)) {
    const parsed = Number(value);
    if (parsed >= 0 && parsed <= 5) {
      return parsed;
    }
  }
  return null;
}

/**
 * Parse a 1-based PDF toolbar page. Invalid or negative values become null.
 *
 * @param value - Raw `pdf_page_number`.
 * @returns Integer ≥ 1, or null.
 */
function parsePdfPageNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value) && value >= 1) {
    return value;
  }
  if (typeof value === "string" && /^(0|[1-9]\d*)$/.test(value)) {
    const parsed = Number(value);
    return parsed >= 1 ? parsed : null;
  }
  return null;
}

/**
 * Parse the exact supporting span. Preserve interior whitespace.
 *
 * @param value - Raw top-level `evidence_excerpt`.
 * @returns The string as sent, or null when missing, empty, or non-string.
 */
function parseEvidenceExcerpt(value: unknown): string | null {
  if (typeof value !== "string" || value === "") {
    return null;
  }
  return value;
}

/**
 * Fetch citations for an owned run.
 *
 * @param auth - Access token.
 * @param runId - Run UUID.
 * @param fetchImpl - Injected fetch.
 * @returns ACL-safe locators and optional top-level excerpts. Provenance snippets stripped.
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
 * Fetch one owned citation after live ACL or HTTPS recheck.
 *
 * @param auth - Access token.
 * @param runId - Owning run UUID.
 * @param citationId - Citation UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Detail row with optional excerpt and HTTPS `source_url`.
 * @throws ClassifiedApiError on non-OK responses.
 */
export async function fetchCitationDetail(
  auth: ApiAuth,
  runId: string,
  citationId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<CitationResponse> {
  const response = await fetchImpl(
    apiUrl(`/runs/${runId}/citations/${citationId}`),
    { headers: resumeHeaders(auth) },
  );
  const body = await readJsonObject(response);
  throwIfNotOk(response, body);
  const parsed = parseCitationItem(body);
  if (parsed === null) {
    throw new ClassifiedApiError(
      classifiedOrGenericFailure(response.status, body, response.headers),
    );
  }
  return parsed;
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
