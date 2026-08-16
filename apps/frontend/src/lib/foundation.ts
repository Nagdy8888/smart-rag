/**
 * Honest capability marker for the Phase 6 thin developer UI.
 *
 * Retrieval quality is proven by API/eval packets, not by this shell.
 * Stitch and production frontend remain later phases.
 */
export const foundationCapability = {
  status: "thin_developer_ui",
  retrievalImplemented: false,
  stitchImplemented: false,
} as const;
