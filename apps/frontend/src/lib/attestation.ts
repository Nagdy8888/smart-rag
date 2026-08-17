/**
 * Uploader attestation values from core governance. The UI does not invent
 * categories. `attestation_policy_version` must match
 * `EXTERNAL_PROCESSING_POLICY_VERSION` (`2026-08-13`).
 */

/** Signed external-processing policy version from `smart_rag_core.ingestion.limits`. */
export const ATTESTATION_POLICY_VERSION = "2026-08-13";

/** CategoryDisposition values accepted on finalize. */
export const DECLARED_CATEGORIES = [
  "allowed",
  "prohibited",
  "mandatory_review",
  "unknown",
] as const;

export type DeclaredCategory = (typeof DECLARED_CATEGORIES)[number];

/** Crawl `content_class` default from `EnqueueWebsiteCrawlRequest`. */
export const CRAWL_CONTENT_CLASS_DEFAULT = "synthetic";

/** Crawl depth default (1–5). */
export const CRAWL_MAX_DEPTH_DEFAULT = 2;

/** Crawl page default (1–200). */
export const CRAWL_MAX_PAGES_DEFAULT = 50;
