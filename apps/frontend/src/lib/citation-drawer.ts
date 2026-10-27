/**
 * Source-drawer contract (GAP-07-09). Citation ids and provenance text only.
 * Company Storage URLs stay non-href. Preview/download are unavailable.
 * Web chips may use a public http(s) URL after `isSafeHttpUrl`.
 */

import { isSafeHttpUrl } from "./safe-text";
import type { CitationResponse } from "./types";

/** Honest GAP copy. No preview HTTP. */
export const SOURCE_PREVIEW_UNAVAILABLE =
  "Source preview and download are not available.";

/** Inference chains are not in the SSE catalog. */
export const INFERENCE_LINKS_UNAVAILABLE =
  "Sources appear as citation chips on the answer.";

/** 404 / IDOR copy. Never interpolates a title. */
export const DOCUMENT_NOT_FOUND_COPY = "Not found.";

/**
 * Return a citation chip href for Web sources only.
 *
 * Company rows always return null so privileged Storage URLs cannot leak
 * into `href`. Web rows require `isSafeHttpUrl`.
 *
 * @param url - Provenance URL candidate.
 * @param sourceKind - Citation discriminator. Defaults to company.
 * @returns Safe http(s) URL, or null.
 */
export function citationChipHref(
  url: unknown,
  sourceKind: CitationResponse["source_kind"] = "company_document",
): string | null {
  if (sourceKind !== "web") {
    return null;
  }
  if (typeof url !== "string" || !isSafeHttpUrl(url)) {
    return null;
  }
  return url;
}

/**
 * Return a chip href from a citation row.
 *
 * @param citation - Authorized citation. Hostile provenance.
 * @returns Safe Web URL, or undefined for company and unsafe URLs.
 */
export function hrefForCitationRecord(
  citation: CitationResponse,
): string | undefined {
  if (citation.source_unavailable) return undefined;
  const url =
    citation.source_url ?? citation.provenance.url ?? citation.provenance.source_url;
  return citationChipHref(url, citation.source_kind) ?? undefined;
}

/**
 * Return whether a provenance URL may be shown as isolated text (not href).
 *
 * @param value - Candidate.
 * @returns True for http(s) only. Storage keys fail `isSafeHttpUrl`.
 */
export function provenanceUrlIsDisplayable(value: unknown): boolean {
  return typeof value === "string" && isSafeHttpUrl(value);
}
