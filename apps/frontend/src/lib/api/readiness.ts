/**
 * Public/operator readiness, meta handshake, and /me.
 */

import type { CurrentUserResponse, MetaResponse, ReadinessResponse } from "../types";
import { ClassifiedApiError, classifyApiError } from "./errors";
import type { ApiAuth } from "./headers";
import { resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";

/** Browser abort budget for public/operator readiness probes, in milliseconds. */
export const HEALTH_READY_TIMEOUT_MS = 8000;

/**
 * GET `/health/ready` without authentication.
 *
 * Public bodies are `status`, `query_ready`, and coarse `detail` only.
 * Named ParadeDB/Valkey/LightRAG probes stay on `GET /ops/ready`.
 *
 * @param fetchImpl - Injected fetch.
 * @returns Readiness payload, or null when the API is unreachable.
 */
export async function fetchReady(
  fetchImpl: typeof fetch = fetch,
): Promise<ReadinessResponse | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HEALTH_READY_TIMEOUT_MS);
  try {
    const response = await fetchImpl(apiUrl("/health/ready"), {
      signal: controller.signal,
    });
    const body = await readJsonObject(response);
    if (!response.ok) {
      return null;
    }
    return {
      status: String(body.status ?? ""),
      query_ready: Boolean(body.query_ready),
      detail: String(body.detail ?? ""),
      rate_limit_degraded: false,
      dependencies: [],
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * GET `/ops/ready` as owner/admin. Members receive 403 and this returns null.
 *
 * @param auth - Bearer token.
 * @param fetchImpl - Injected fetch.
 * @returns Named dependency probes, or null when forbidden or unreachable.
 */
export async function fetchOperatorReady(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<ReadinessResponse | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HEALTH_READY_TIMEOUT_MS);
  try {
    const response = await fetchImpl(apiUrl("/ops/ready"), {
      signal: controller.signal,
      headers: resumeHeaders(auth),
    });
    if (response.status === 401 || response.status === 403) {
      return null;
    }
    const body = await readJsonObject(response);
    if (!response.ok) {
      return null;
    }
    const rawDeps = body.dependencies;
    const dependencies = Array.isArray(rawDeps)
      ? rawDeps
          .filter(
            (item): item is Record<string, unknown> =>
              item !== null && typeof item === "object" && !Array.isArray(item),
          )
          .map((item) => ({
            name: String(item.name ?? ""),
            status: String(item.status ?? ""),
          }))
      : [];
    return {
      status: String(body.status ?? ""),
      query_ready: Boolean(body.query_ready),
      detail: String(body.detail ?? ""),
      rate_limit_degraded: Boolean(body.rate_limit_degraded),
      dependencies,
    };
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Overlay operator named probes onto the public ready body.
 *
 * @param publicReady - `GET /health/ready` mapping, or null.
 * @param operatorReady - `GET /ops/ready` mapping, or null when forbidden.
 * @returns Merged console payload, or null when public ready is unreachable.
 */
export function mergeReadiness(
  publicReady: ReadinessResponse | null,
  operatorReady: ReadinessResponse | null,
): ReadinessResponse | null {
  if (publicReady === null) {
    return null;
  }
  if (operatorReady === null) {
    return publicReady;
  }
  return {
    ...publicReady,
    ...operatorReady,
    dependencies: operatorReady.dependencies,
  };
}

/**
 * Public ready plus owner/admin named probes when the Bearer is allowed.
 *
 * @param auth - Access token, or null on the signed-out login page.
 * @param role - `/me` role. Operator probes run only for `owner` or `admin`.
 * @param fetchImpl - Injected fetch.
 * @returns Merged console readiness, or null when FastAPI is unreachable.
 */
export async function loadConsoleReadiness(
  auth: ApiAuth | null,
  role?: string | null,
  fetchImpl: typeof fetch = fetch,
): Promise<ReadinessResponse | null> {
  const publicReady = await fetchReady(fetchImpl);
  if (publicReady === null || auth === null) {
    return publicReady;
  }
  if (role !== "owner" && role !== "admin") {
    return publicReady;
  }
  const operatorReady = await fetchOperatorReady(auth, fetchImpl);
  return mergeReadiness(publicReady, operatorReady);
}

/**
 * GET `/api/meta` without authentication.
 *
 * @param fetchImpl - Injected fetch.
 * @returns Handshake fields.
 * @throws Error when the response is not ok, unparsable, or times out after 8s.
 */
export async function fetchMeta(
  fetchImpl: typeof fetch = fetch,
): Promise<MetaResponse> {
  const response = await fetchImpl(apiUrl("/api/meta"), {
    signal: AbortSignal.timeout(8_000),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throw new Error("meta_unreachable");
  }
  const minClientVersion = String(body.min_client_version ?? "");
  if (minClientVersion.trim() === "") {
    throw new Error("meta_unreachable");
  }
  return {
    api_version: String(body.api_version ?? ""),
    sse_schema_version: String(body.sse_schema_version ?? ""),
    min_client_version: minClientVersion,
    pdf_eval_workspace: body.pdf_eval_workspace === true,
  };
}

/**
 * GET `/me` with a Bearer token.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Server-derived caller snapshot.
 * @throws Error `session_revoked` when FastAPI returns that detail.
 * @throws ClassifiedApiError on other 401/403 bodies so Ask can show the
 *   session-rejected banner. Other failures stay `me_failed`.
 */
export async function fetchMe(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<CurrentUserResponse> {
  const response = await fetchImpl(apiUrl("/me"), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    const classified = classifyApiError(response.status, body);
    if (classified?.kind === "auth" && classified.detail === "session_revoked") {
      throw new Error("session_revoked");
    }
    if (classified?.kind === "auth") {
      throw new ClassifiedApiError(classified);
    }
    throw new Error("me_failed");
  }
  return {
    user_id: String(body.user_id ?? ""),
    role: String(body.role ?? ""),
    authorization_version: Number(body.authorization_version ?? 0),
    upload_enabled: Boolean(body.upload_enabled),
  };
}
