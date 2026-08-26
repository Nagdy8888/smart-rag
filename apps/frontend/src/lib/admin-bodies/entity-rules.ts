/**
 * Extra-forbid entity-rule upsert, suggest, and concurrency bodies.
 */

import {
  ENTITY_RULE_SOURCES,
  ENTITY_RULE_STATUSES,
  type EntityRuleConcurrencyRequest,
  type EntityRuleSource,
  type EntityRuleStatus,
  type EntityRuleSuggestRequest,
  type EntityRuleUpsertRequest,
} from "../types";

/**
 * Build `{ row_version }` for approve or revoke.
 *
 * @param rowVersion - Optimistic concurrency token. Extra keys are dropped.
 * @returns Concurrency body.
 */
export function buildEntityRuleConcurrencyBody(
  rowVersion: number,
): EntityRuleConcurrencyRequest {
  const version = Number.isFinite(rowVersion) ? Math.max(1, Math.floor(rowVersion)) : 1;
  return { row_version: version };
}

/**
 * Build an entity-rule upsert without unknown fields.
 *
 * @param input - Upsert form. Extra keys such as `sql` are dropped.
 * @returns Upsert body.
 */
export function buildEntityRuleUpsertBody(
  input: EntityRuleUpsertRequest & Record<string, unknown>,
): EntityRuleUpsertRequest {
  const source = (ENTITY_RULE_SOURCES as readonly string[]).includes(
    String(input.source ?? "admin"),
  )
    ? (input.source as EntityRuleSource)
    : "admin";
  const status = (ENTITY_RULE_STATUSES as readonly string[]).includes(
    String(input.status ?? "approved"),
  )
    ? (input.status as EntityRuleStatus)
    : "approved";
  const body: EntityRuleUpsertRequest = {
    entity_type: String(input.entity_type ?? ""),
    canonical_name: String(input.canonical_name ?? ""),
    aliases: Array.isArray(input.aliases)
      ? input.aliases.map(String).slice(0, 32)
      : [],
    do_not_merge: Array.isArray(input.do_not_merge)
      ? input.do_not_merge.map(String).slice(0, 32)
      : [],
    source,
    status,
  };
  if (typeof input.display_label === "string" && input.display_label) {
    body.display_label = input.display_label;
  }
  if (Array.isArray(input.languages)) {
    body.languages = input.languages.map(String).slice(0, 8);
  }
  if (input.alias_scope === "company" || input.alias_scope === "synthetic_eval") {
    body.alias_scope = input.alias_scope;
  }
  if (
    input.relation_label_policy === "directed" ||
    input.relation_label_policy === "symmetric"
  ) {
    body.relation_label_policy = input.relation_label_policy;
  }
  if (typeof input.reason === "string") {
    body.reason = input.reason;
  }
  if (typeof input.confidence === "number") {
    body.confidence = input.confidence;
  }
  if (typeof input.row_version === "number") {
    body.row_version = input.row_version;
  }
  return body;
}

/**
 * Build a suggestion body. Status and row_version are omitted.
 *
 * @param input - Suggestion form. Extra keys are dropped.
 * @returns Suggestion POST body with source default `feedback`.
 */
export function buildEntityRuleSuggestBody(
  input: EntityRuleSuggestRequest & Record<string, unknown>,
): EntityRuleSuggestRequest {
  const upsert = buildEntityRuleUpsertBody({
    ...input,
    source: input.source ?? "feedback",
    status: "suggested",
  });
  const body: EntityRuleSuggestRequest = {
    entity_type: upsert.entity_type,
    canonical_name: upsert.canonical_name,
    aliases: upsert.aliases,
    do_not_merge: upsert.do_not_merge,
    source: upsert.source === "admin" ? "feedback" : upsert.source,
  };
  if (upsert.display_label) {
    body.display_label = upsert.display_label;
  }
  if (upsert.languages) {
    body.languages = upsert.languages;
  }
  if (upsert.alias_scope) {
    body.alias_scope = upsert.alias_scope;
  }
  if (upsert.relation_label_policy) {
    body.relation_label_policy = upsert.relation_label_policy;
  }
  if (typeof upsert.reason === "string") {
    body.reason = upsert.reason;
  }
  if (typeof upsert.confidence === "number") {
    body.confidence = upsert.confidence;
  }
  return body;
}
