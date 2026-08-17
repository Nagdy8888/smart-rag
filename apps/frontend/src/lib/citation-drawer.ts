/**
 * Source-drawer contract (GAP-07-09). Citation ids and provenance text only.
 * No privileged Storage URL. Preview/download are unavailable.
 */

import { isSafeHttpUrl } from "./safe-text";

/** Honest GAP copy. No preview HTTP. */
export const SOURCE_PREVIEW_UNAVAILABLE =
  "Source preview and download are unavailable (GAP-07-09).";

/** Inference chains are not in the SSE catalog. */
export const INFERENCE_LINKS_UNAVAILABLE =
  "Inference-chain objects are not in the SSE catalog (GAP-07-02). Citation chips show authorized ids only.";

/** Document delete HTTP does not exist. */
export const DOCUMENT_DELETE_UNAVAILABLE =
  "Document deletion is unavailable (GAP-07-14).";

/** 404 / IDOR copy. Never interpolates a title. */
export const DOCUMENT_NOT_FOUND_COPY = "Not found.";

/**
 * Return a citation chip href. Always `null` in this packet so privileged
 * Storage URLs cannot leak into `href`.
 *
 * Public http(s) provenance URLs are shown as text, not as anchors.
 *
 * @param _url - Provenance URL candidate. Ignored for `href`.
 * @returns Always `null`.
 */
export function citationChipHref(_url: unknown): null {
  void _url;
  return null;
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
