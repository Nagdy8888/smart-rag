/**
 * Entity-rule HTTP helpers.
 */

import type {
  EntityRuleListItem,
  EntityRuleListResponse,
  EntityRuleMutationResponse,
  EntityRuleSource,
  EntityRuleStatus,
  EntityRuleSuggestRequest,
  EntityRuleUpsertRequest,
} from "../types";
import {
  buildEntityRuleConcurrencyBody,
  buildEntityRuleSuggestBody,
  buildEntityRuleUpsertBody,
} from "../admin-bodies";
import { throwClassifiedAdminError } from "./admin-errors";
import type { ApiAuth } from "./headers";
import { adminMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";

/**
 * Parse one entity-rule list row.
 *
 * @param row - JSON object.
 * @returns List item.
 */
function parseEntityRuleItem(row: Record<string, unknown>): EntityRuleListItem {
  const aliases = Array.isArray(row.aliases) ? row.aliases.map(String) : [];
  const doNotMerge = Array.isArray(row.do_not_merge)
    ? row.do_not_merge.map(String)
    : [];
  const languages = Array.isArray(row.languages) ? row.languages.map(String) : [];
  return {
    id: String(row.id ?? ""),
    entity_type: String(row.entity_type ?? ""),
    canonical_name: typeof row.canonical_name === "string" ? row.canonical_name : null,
    display_label: typeof row.display_label === "string" ? row.display_label : null,
    aliases,
    do_not_merge: doNotMerge,
    languages,
    alias_scope: String(row.alias_scope ?? ""),
    relation_label_policy: String(row.relation_label_policy ?? ""),
    status: String(row.status ?? "suggested") as EntityRuleStatus,
    active: Boolean(row.active),
    row_version: Number(row.row_version ?? 1),
    source: String(row.source ?? "admin") as EntityRuleSource,
    reason: String(row.reason ?? ""),
    confidence: typeof row.confidence === "number" ? row.confidence : null,
    created_at: typeof row.created_at === "string" ? row.created_at : null,
    updated_at: typeof row.updated_at === "string" ? row.updated_at : null,
  };
}

/**
 * List entity rules. Owner/admin on the server; members 403.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns `{ rules }`.
 */
export async function listEntityRules(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<EntityRuleListResponse> {
  const response = await fetchImpl(apiUrl("/admin/graph/entity-rules"), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  const rulesRaw = Array.isArray(body.rules) ? body.rules : [];
  return {
    rules: rulesRaw
      .filter(
        (item): item is Record<string, unknown> =>
          item !== null && typeof item === "object" && !Array.isArray(item),
      )
      .map(parseEntityRuleItem),
  };
}

/**
 * Parse an entity-rule mutation response.
 *
 * @param body - JSON object.
 * @returns Mutation identifiers. Alias text is omitted.
 */
function parseEntityRuleMutation(
  body: Record<string, unknown>,
): EntityRuleMutationResponse {
  return {
    rule_id: String(body.rule_id ?? ""),
    status: String(body.status ?? "suggested") as EntityRuleStatus,
    row_version: Number(body.row_version ?? 1),
    entity_rules_generation: Number(body.entity_rules_generation ?? 0),
    rebuild_job_id:
      typeof body.rebuild_job_id === "string" ? body.rebuild_job_id : null,
    repair_job_id: typeof body.repair_job_id === "string" ? body.repair_job_id : null,
    invalidated: Boolean(body.invalidated),
  };
}

/**
 * Create or replace an entity rule. Extra fields are omitted.
 *
 * @param auth - Access token.
 * @param input - Upsert payload.
 * @param fetchImpl - Injected fetch.
 * @returns Mutation identifiers.
 */
export async function upsertEntityRule(
  auth: ApiAuth,
  input: EntityRuleUpsertRequest & Record<string, unknown>,
  fetchImpl: typeof fetch = fetch,
): Promise<EntityRuleMutationResponse> {
  const payload = buildEntityRuleUpsertBody(input);
  const response = await fetchImpl(apiUrl("/admin/graph/entity-rules"), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseEntityRuleMutation(body);
}

/**
 * Approve a suggested entity rule. Body is `{ row_version }` only.
 *
 * @param auth - Access token.
 * @param ruleId - Rule UUID.
 * @param rowVersion - Optimistic concurrency token.
 * @param fetchImpl - Injected fetch.
 * @returns Mutation identifiers.
 * @throws Error `stale_row_version` on 409.
 */
export async function approveEntityRule(
  auth: ApiAuth,
  ruleId: string,
  rowVersion: number,
  fetchImpl: typeof fetch = fetch,
): Promise<EntityRuleMutationResponse> {
  const response = await fetchImpl(
    apiUrl(`/admin/graph/entity-rules/${ruleId}/approve`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify(buildEntityRuleConcurrencyBody(rowVersion)),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseEntityRuleMutation(body);
}

/**
 * Revoke an entity rule. Body is `{ row_version }` only.
 *
 * @param auth - Access token.
 * @param ruleId - Rule UUID.
 * @param rowVersion - Optimistic concurrency token.
 * @param fetchImpl - Injected fetch.
 * @returns Mutation identifiers.
 */
export async function revokeEntityRule(
  auth: ApiAuth,
  ruleId: string,
  rowVersion: number,
  fetchImpl: typeof fetch = fetch,
): Promise<EntityRuleMutationResponse> {
  const response = await fetchImpl(
    apiUrl(`/admin/graph/entity-rules/${ruleId}/revoke`),
    {
      method: "POST",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify(buildEntityRuleConcurrencyBody(rowVersion)),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseEntityRuleMutation(body);
}

/**
 * PATCH one entity rule including `row_version`.
 *
 * @param auth - Access token.
 * @param ruleId - Rule UUID.
 * @param input - Upsert fields plus concurrency token.
 * @param fetchImpl - Injected fetch.
 * @returns Mutation identifiers.
 * @throws Error `stale_row_version` on 409.
 */
export async function patchEntityRule(
  auth: ApiAuth,
  ruleId: string,
  input: EntityRuleUpsertRequest & Record<string, unknown>,
  fetchImpl: typeof fetch = fetch,
): Promise<EntityRuleMutationResponse> {
  const payload = buildEntityRuleUpsertBody(input);
  const response = await fetchImpl(
    apiUrl(`/admin/graph/entity-rules/${ruleId}`),
    {
      method: "PATCH",
      headers: adminMutationHeaders(auth),
      body: JSON.stringify(payload),
    },
  );
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseEntityRuleMutation(body);
}

/**
 * Store an inactive suggestion. Never auto-approves.
 *
 * @param auth - Access token.
 * @param input - Suggestion payload.
 * @param fetchImpl - Injected fetch.
 * @returns Mutation identifiers with `invalidated=false` on success.
 */
export async function suggestEntityRule(
  auth: ApiAuth,
  input: EntityRuleSuggestRequest & Record<string, unknown>,
  fetchImpl: typeof fetch = fetch,
): Promise<EntityRuleMutationResponse> {
  const payload = buildEntityRuleSuggestBody(input);
  const response = await fetchImpl(apiUrl("/admin/graph/entity-rules/suggestions"), {
    method: "POST",
    headers: adminMutationHeaders(auth),
    body: JSON.stringify(payload),
  });
  const body = await readJsonObject(response);
  if (!response.ok) {
    throwClassifiedAdminError(response.status, body, response.headers);
  }
  return parseEntityRuleMutation(body);
}
