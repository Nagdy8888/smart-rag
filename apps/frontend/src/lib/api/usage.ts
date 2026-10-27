import { parseCheckpointUsage, parseDisplayCost } from "../checkpoint-usage";
import { parseCostReporting } from "../cost-reporting";
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
  const counters = [body.prompt_tokens, body.completion_tokens, body.usage_rows];
  if (
    (body.scope !== "me" && body.scope !== "company") ||
    (typeof cost !== "number" && typeof cost !== "string") ||
    (typeof cost === "string" && cost.trim() === "") ||
    !Number.isFinite(Number(cost)) || Number(cost) < 0 ||
    counters.some((value) => typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
  ) {
    throw new Error("invalid_usage_response");
  }
  return {
    scope: body.scope,
    cost_usd: cost,
    ...(body.cost_reporting === undefined ? {} : {cost_reporting:parseCostReporting(body.cost_reporting)}),
    ...(body.checkpoint_usage === undefined ? {} : {checkpoint_usage:parseCheckpointUsage(body.checkpoint_usage)}),
    ...(body.display_cost_usd === undefined ? {} : {display_cost_usd:parseDisplayCost(body.display_cost_usd)}),
    prompt_tokens: body.prompt_tokens as number,
    completion_tokens: body.completion_tokens as number,
    usage_rows: body.usage_rows as number,
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
