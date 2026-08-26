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

/** FastAPI `q` min_length. */
export const GRAPH_SEARCH_MIN_LENGTH = 1;

/** FastAPI `q` max_length. */
export const GRAPH_SEARCH_MAX_QUERY = 128;

/** Inspect row cap. */
export const GRAPH_INSPECT_MAX_ROWS = 200;

/** Empty inspect list. */
export const EMPTY_INSPECT_COPY =
  "No authorized graph evidence matched this inspection.";

/** Chip cap helper. */
export const GRAPH_ENTITY_LIMIT_COPY = "You can inspect up to 12 entities.";

/** Visible truthful inspect bounds. */
export const GRAPH_INSPECT_BOUNDS_COPY =
  "Inspect is capped at 12 entities, depth 3, and 200 nodes.";

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

/**
 * Return whether a limitation is a graph outage or fallback, distinct from
 * Graph Pending and ACL blindness.
 *
 * @param code - Limitation code.
 * @returns True for outage/survival/empty/deadline codes.
 */
export function isGraphOutageLimitation(code: string): boolean {
  return (
    code === "graph_outage" ||
    code === "graph_survival_below_threshold" ||
    code === "graph_empty" ||
    code === "graph_deadline"
  );
}

/**
 * Clamp a search string to the FastAPI `q` contract.
 *
 * @param value - Draft query.
 * @returns Trimmed string of at most 128 characters.
 */
export function clampGraphSearchQuery(value: string): string {
  return value.trim().slice(0, GRAPH_SEARCH_MAX_QUERY);
}

/**
 * Return whether a trimmed query meets the search minimum.
 *
 * @param value - Draft query.
 * @returns True when FastAPI will accept `q`.
 */
export function graphSearchQueryIsRunnable(value: string): boolean {
  return clampGraphSearchQuery(value).length >= GRAPH_SEARCH_MIN_LENGTH;
}

/**
 * Cap inspect nodes at 200 for display.
 *
 * @param nodes - Inspect rows.
 * @returns At most `GRAPH_INSPECT_MAX_ROWS` rows.
 */
export function visibleInspectNodes<T>(nodes: readonly T[]): T[] {
  return nodes.slice(0, GRAPH_INSPECT_MAX_ROWS);
}
