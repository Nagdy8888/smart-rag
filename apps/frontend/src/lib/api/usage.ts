/**
 * Caller and company usage HTTP helpers.
 */

import type { UsageResponse } from "../types";
import { throwClassifiedAdminError } from "./admin-errors";
import type { ApiAuth } from "./headers";
import { resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";

/**
 * Parse usage totals. Prompt text fields are omitted even if present.
 *
 * @param body - JSON object.
 * @returns Totals only.
 */
function parseUsageResponse(body: Record<string, unknown>): UsageResponse {
  const cost = body.cost_usd;
  return {
    scope: String(body.scope ?? ""),
    cost_usd:
      typeof cost === "number" || typeof cost === "string" ? cost : String(cost ?? "0"),
    prompt_tokens: Number(body.prompt_tokens ?? 0),
    completion_tokens: Number(body.completion_tokens ?? 0),
    usage_rows: Number(body.usage_rows ?? 0),
  };
}

/**
 * Fetch caller usage totals without prompt text.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Usage summary.
 * @throws Error when FastAPI rejects the call.
 */
export async function fetchUsageMe(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<UsageResponse> {
  const response = await fetchImpl(apiUrl("/usage/me"), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseUsageResponse(body);
}

/**
 * Fetch company usage totals. Owner/admin on the server; members 403.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Company totals. No prompt text.
 * @throws Error `forbidden` for member/viewer 403.
 */
export async function fetchUsageCompany(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<UsageResponse> {
  const response = await fetchImpl(apiUrl("/usage/company"), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseUsageResponse(body);
}
