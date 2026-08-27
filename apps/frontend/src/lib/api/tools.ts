/**
 * Tool catalog and admin-tool HTTP helpers.
 */

import type { ToolCardResponse, ToolMutationResponse, ToolPermissionRequest, ToolSeedRequest } from "../types";
import {
  buildToolEnableBody,
  buildToolPermissionBody,
  buildToolSeedBody,
} from "../admin-bodies";
import { throwClassifiedAdminError } from "./admin-errors";
import type { ApiAuth } from "./headers";
import { adminMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";

/**
 * Parse one tool card. Unknown extra fields are ignored.
 *
 * @param row - JSON object.
 * @returns Card, or null when `tool_key` is empty.
 */
function parseToolCard(row: Record<string, unknown>): ToolCardResponse | null {
  const toolKey = String(row.tool_key ?? "");
  if (toolKey === "") {
    return null;
  }
  return {
    tool_key: toolKey,
    version_label: String(row.version_label ?? ""),
    short_name: String(row.short_name ?? ""),
    purpose: String(row.purpose ?? ""),
    required_role: String(row.required_role ?? ""),
    risk_class: String(row.risk_class ?? ""),
    active: Boolean(row.active),
  };
}

/**
 * List tools the live role may see. Unauthorized names are omitted.
 *
 * This client does not invent redacted titles for omitted tools.
 *
 * @param auth - Access token.
 * @param query - Optional substring filter.
 * @param fetchImpl - Injected fetch.
 * @returns Permission-filtered cards.
 */
export async function listTools(
  auth: ApiAuth,
  query?: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ToolCardResponse[]> {
  const suffix =
    query && query.trim() !== ""
      ? `?q=${encodeURIComponent(query.trim().slice(0, 64))}`
      : "";
  const response = await fetchImpl(apiUrl(`/tools${suffix}`), {
    headers: resumeHeaders(auth),
  });
  let parsed: unknown = [];
  try {
    parsed = await response.json();
  } catch {
    parsed = {};
  }
  if (!response.ok) {
    const body =
      parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
        ? (parsed as Record<string, unknown>)
        : {};
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  if (!Array.isArray(parsed)) {
    throw new Error("request_rejected");
  }
  return parsed
    .filter(
      (item): item is Record<string, unknown> =>
        item !== null && typeof item === "object" && !Array.isArray(item),
    )
    .map(parseToolCard)
    .filter((card): card is ToolCardResponse => card !== null);
}

/**
 * Seed an allow-listed tool. Owner/admin on the server.
 *
 * @param auth - Access token.
 * @param input - Seed payload.
 * @param fetchImpl - Injected fetch.
 * @returns Catalog row id.
 */
export async function seedTool(
  auth: ApiAuth,
  input: ToolSeedRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<ToolMutationResponse> {
  const payload = buildToolSeedBody(input);
  const response = await fetchImpl(apiUrl("/admin/tools"), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return { id: String(body.id ?? "") };
}

/**
 * Enable or disable a catalog tool. Owner/admin on the server.
 *
 * The helper still exists for viewer/member callers; FastAPI returns 403.
 *
 * @param auth - Access token. Bearer only; no role header.
 * @param toolKey - Catalog key.
 * @param active - Desired flag.
 * @param fetchImpl - Injected fetch.
 * @returns Catalog row id.
 */
export async function enableTool(
  auth: ApiAuth,
  toolKey: string,
  active: boolean,
  fetchImpl: typeof fetch = fetch,
): Promise<ToolMutationResponse> {
  const response = await fetchImpl(apiUrl(`/admin/tools/${toolKey}/enable`), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(buildToolEnableBody(active)),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return { id: String(body.id ?? "") };
}

/**
 * Set a role permission seed. Executor still rechecks live role.
 *
 * @param auth - Access token.
 * @param toolKey - Catalog key.
 * @param input - Target role and permission.
 * @param fetchImpl - Injected fetch.
 * @returns Permission row id.
 */
export async function setToolPermission(
  auth: ApiAuth,
  toolKey: string,
  input: ToolPermissionRequest,
  fetchImpl: typeof fetch = fetch,
): Promise<ToolMutationResponse> {
  const payload = buildToolPermissionBody(input);
  const response = await fetchImpl(
    apiUrl(`/admin/tools/${toolKey}/permissions`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify(payload),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return { id: String(body.id ?? "") };
}
