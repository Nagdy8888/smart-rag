/**
 * Bounded graph inspect/search helpers. Depth never exceeds 3 on this client.
 * ACL-blindness copy ignores unauthorized counts even when present.
 */

import { limitationCopy } from "./limitations";
import type { GraphInspectLimitation, GraphInspectRequest } from "./types";

/** Hop cap matching `GraphInspectRequest.depth` le=3. */
export const GRAPH_INSPECT_MAX_DEPTH = 3;

/** Entity-key cap matching the FastAPI schema. */
export const GRAPH_INSPECT_MAX_ENTITIES = 12;

/** Search `limit` cap. */
export const GRAPH_SEARCH_MAX_LIMIT = 25;

/** Inspect row cap. */
export const GRAPH_INSPECT_MAX_ROWS = 200;

/**
 * Clamp inspect depth to 1–3. Default 3.
 *
 * @param depth - Raw user or query value.
 * @returns Integer in `[1, 3]`.
 */
export function clampGraphInspectDepth(depth: number): number {
  if (!Number.isFinite(depth)) {
    return GRAPH_INSPECT_MAX_DEPTH;
  }
  return Math.min(
    GRAPH_INSPECT_MAX_DEPTH,
    Math.max(1, Math.floor(depth)),
  );
}

/**
 * Clamp entity-search limit to 1–25.
 *
 * @param limit - Raw limit.
 * @returns Integer in `[1, 25]`.
 */
export function clampGraphSearchLimit(limit: number): number {
  if (!Number.isFinite(limit)) {
    return GRAPH_SEARCH_MAX_LIMIT;
  }
  return Math.min(GRAPH_SEARCH_MAX_LIMIT, Math.max(1, Math.floor(limit)));
}

/**
 * Build a `GraphInspectRequest` with clamped depth and at most 12 keys.
 *
 * @param entityKeys - Raw keys.
 * @param documentId - Optional document seed.
 * @param depth - Requested hop count.
 * @returns Body ready for `POST /graph/inspect`.
 */
export function buildGraphInspectRequest(
  entityKeys: readonly string[],
  documentId: string | null,
  depth: number,
): GraphInspectRequest {
  const keys = entityKeys
    .map((key) => key.trim())
    .filter((key) => key.length > 0 && key.length <= 64)
    .slice(0, GRAPH_INSPECT_MAX_ENTITIES);
  return {
    entity_keys: keys,
    document_id: documentId && documentId.trim() !== "" ? documentId : null,
    depth: clampGraphInspectDepth(depth),
  };
}

/**
 * Signed ACL-blindness sentence. Never interpolates `count` or titles.
 *
 * @returns Exact copy from the packet contract.
 */
export function graphAclBlindnessCopy(): string {
  return "Some sources you cannot access are omitted.";
}

/**
 * Render one inspect limitation. ACL blindness ignores `count`.
 *
 * @param limitation - Server `{code, count?}`.
 * @returns Signed sentence without unauthorized counts.
 */
export function graphLimitationDisplay(
  limitation: GraphInspectLimitation,
): string {
  if (limitation.code === "graph_acl_blindness") {
    return graphAclBlindnessCopy();
  }
  return limitationCopy(limitation.code);
}

/**
 * Return whether a limitation is Graph Pending (authorized not-ready),
 * distinct from ACL blindness.
 *
 * @param code - Limitation code.
 * @returns True for pending/updating/partial-readiness codes.
 */
export function isGraphPendingLimitation(code: string): boolean {
  return (
    code === "graph_updating" ||
    code === "graph_partial_readiness" ||
    code === "graph_pending"
  );
}
