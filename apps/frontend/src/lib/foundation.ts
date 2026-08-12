/**
 * Honest capability marker for the Phase 1 frontend foundation.
 *
 * No authentication, retrieval, ingestion, or model success is represented.
 */
export const foundationCapability = {
  status: "unconfigured",
  retrievalImplemented: false,
} as const;
