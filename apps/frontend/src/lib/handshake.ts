/**
 * Compatibility admission before paid FastAPI mutations.
 *
 * Resume GET does not repeat this handshake (`docs/api/SSE.md`).
 */

import {
  CLIENT_SSE_SCHEMA_VERSION,
  CLIENT_VERSION,
  clientVersionIsSupported,
} from "./client-version";
import type { MetaResponse, ReadinessResponse } from "./types";

/** Outcome of comparing local pins to `GET /api/meta`. */
export type HandshakeDecision = {
  /** False blocks `startMessageStream` / upload reserve. Resume GET may still run. */
  allowPaidPost: boolean;
  kind: "ok" | "loading" | "unreachable" | "below_min" | "schema_newer";
  minClientVersion: string | null;
  sseSchemaVersion: string | null;
};

/**
 * Copy shown when the local pin is below `min_client_version`.
 *
 * @returns Exact brief sentence. Never includes stack traces.
 */
export function handshakeBelowMinCopy(): string {
  return "This page is out of date. Reload to get the latest version.";
}

/** Copy when core `query_ready` is false. Optional BM25/graph degradation is not this. */
export const QUERY_NOT_READY_COPY =
  "Search isn’t ready yet. Try again in a moment.";

/**
 * Compare published SSE schema labels. Numeric strings use integer order;
 * otherwise lexicographic. Equal or unparsable-as-int pairs are not "newer".
 *
 * @param published - `meta.sse_schema_version`.
 * @param clientCatalog - `CLIENT_SSE_SCHEMA_VERSION`.
 * @returns True when the API advertises a newer additive schema.
 */
export function isSseSchemaNewerThanCatalog(
  published: string,
  clientCatalog: string,
): boolean {
  const publishedTrim = published.trim();
  const catalogTrim = clientCatalog.trim();
  if (publishedTrim === "" || catalogTrim === "") {
    return false;
  }
  const publishedNum = Number.parseInt(publishedTrim, 10);
  const catalogNum = Number.parseInt(catalogTrim, 10);
  if (Number.isFinite(publishedNum) && Number.isFinite(catalogNum)) {
    return publishedNum > catalogNum;
  }
  return publishedTrim > catalogTrim;
}

/**
 * Decide whether a new paid POST may run.
 *
 * Unreachable or unparsable meta fails closed for new spend. A newer SSE
 * schema is not a block: unknown events are ignored.
 *
 * @param meta - Handshake body, or null when the query failed.
 * @param metaStatus - TanStack status. `loading` waits; `error` fails closed.
 * @param clientVersion - Defaults to `CLIENT_VERSION`.
 * @param clientSseSchemaVersion - Defaults to `CLIENT_SSE_SCHEMA_VERSION`.
 * @returns Decision used to disable the composer before `startMessageStream`.
 */
export function evaluatePaidHandshake(
  meta: MetaResponse | null,
  metaStatus: "loading" | "ok" | "error",
  clientVersion: string = CLIENT_VERSION,
  clientSseSchemaVersion: string = CLIENT_SSE_SCHEMA_VERSION,
): HandshakeDecision {
  if (metaStatus === "loading") {
    return {
      allowPaidPost: false,
      kind: "loading",
      minClientVersion: null,
      sseSchemaVersion: null,
    };
  }
  if (metaStatus === "error" || meta === null) {
    return {
      allowPaidPost: false,
      kind: "unreachable",
      minClientVersion: null,
      sseSchemaVersion: null,
    };
  }
  const minimum = meta.min_client_version;
  if (!clientVersionIsSupported(clientVersion, minimum)) {
    return {
      allowPaidPost: false,
      kind: "below_min",
      minClientVersion: minimum,
      sseSchemaVersion: meta.sse_schema_version,
    };
  }
  if (isSseSchemaNewerThanCatalog(meta.sse_schema_version, clientSseSchemaVersion)) {
    return {
      allowPaidPost: true,
      kind: "schema_newer",
      minClientVersion: minimum,
      sseSchemaVersion: meta.sse_schema_version,
    };
  }
  return {
    allowPaidPost: true,
    kind: "ok",
    minClientVersion: minimum,
    sseSchemaVersion: meta.sse_schema_version,
  };
}

/**
 * Return whether Send may run. Resume of an existing non-terminal run is
 * allowed even when a new paid POST would be blocked.
 *
 * @param decision - Handshake result.
 * @param run - Current chat pointer.
 * @returns True when POST or resume is permitted.
 */
export function mayStartPaidPost(
  decision: HandshakeDecision,
  run: { runId: string | null; terminal: string | null },
): boolean {
  if (run.runId !== null && run.terminal === null) {
    return true;
  }
  return decision.allowPaidPost;
}

export type PaidSendBlock = {
  reason: string;
};

/**
 * Return why a new paid Send is blocked. In-flight resume is not a new POST.
 *
 * BM25 or graph degradation does not block Hybrid. Only handshake failure or
 * `query_ready=false` blocks a new question.
 *
 * @param decision - Meta handshake.
 * @param ready - Console readiness, or undefined while loading.
 * @param run - Current chat pointer.
 * @returns Block reason, or null when Send may proceed (draft aside).
 */
export function paidSendBlockReason(
  decision: HandshakeDecision,
  ready: ReadinessResponse | null | undefined,
  run: { runId: string | null; terminal: string | null },
): string | null {
  if (run.runId !== null && run.terminal === null) {
    return null;
  }
  if (!decision.allowPaidPost) {
    if (decision.kind === "below_min") {
      return handshakeBelowMinCopy();
    }
    if (decision.kind === "loading") {
      return "Connecting…";
    }
    return "Can’t reach the server. Check your connection and try again.";
  }
  if (ready === undefined) {
    return "Checking that search is ready…";
  }
  if (ready === null || ready.query_ready !== true) {
    return QUERY_NOT_READY_COPY;
  }
  return null;
}
