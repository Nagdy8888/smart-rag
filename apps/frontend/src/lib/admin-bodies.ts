/**
 * Extra-forbid builders for administration POST bodies.
 *
 * SQL-like and unknown fields are omitted even when callers pass them.
 */

import {
  ENTITY_RULE_SOURCES,
  ENTITY_RULE_STATUSES,
  GLOSSARY_ENTRY_TYPES,
  GLOSSARY_LANGUAGES,
  GLOSSARY_SCOPES,
  INVITE_ROLES,
  TOOL_PERMISSIONS,
  type CreateInvitationRequest,
  type EntityRuleConcurrencyRequest,
  type EntityRuleSource,
  type EntityRuleStatus,
  type EntityRuleSuggestRequest,
  type EntityRuleUpsertRequest,
  type GlossaryAliasRequest,
  type GlossaryEntryRequest,
  type GlossaryEntryType,
  type GlossaryLanguage,
  type GlossaryScope,
  type ImportGlossaryRequest,
  type InviteRole,
  type ToolPermission,
  type ToolPermissionRequest,
  type ToolSeedRequest,
} from "./types";

const ENTRY_KEY_RE = /^[A-Za-z0-9._:-]+$/;

/**
 * Return whether a role is an invitation target.
 *
 * @param value - Candidate role.
 * @returns True for owner|admin|member|viewer.
 */
export function isInviteRole(value: string): value is InviteRole {
  return (INVITE_ROLES as readonly string[]).includes(value);
}

/**
 * Build `{ email, role, upload_enabled }` only.
 *
 * @param input - Invite form values. Extra keys such as `sql` are dropped.
 * @returns Create-invitation body.
 */
export function buildInvitationCreateBody(
  input: CreateInvitationRequest & Record<string, unknown>,
): CreateInvitationRequest {
  const role = isInviteRole(String(input.role)) ? input.role : "viewer";
  const uploadEnabled = role === "viewer" ? false : Boolean(input.upload_enabled);
  return {
    email: String(input.email ?? ""),
    role,
    upload_enabled: uploadEnabled,
  };
}

/**
 * Build tool seed `{ tool_key, display_name, description?, active? }`.
 *
 * @param input - Seed form. Extra keys are dropped.
 * @returns Seed body.
 */
export function buildToolSeedBody(
  input: ToolSeedRequest & Record<string, unknown>,
): ToolSeedRequest {
  const body: ToolSeedRequest = {
    tool_key: String(input.tool_key ?? ""),
    display_name: String(input.display_name ?? ""),
  };
  if (typeof input.description === "string" && input.description.length > 0) {
    body.description = input.description;
  }
  if (typeof input.active === "boolean") {
    body.active = input.active;
  }
  return body;
}

/**
 * Build `{ active }` for enable/disable.
 *
 * @param active - Desired catalog flag.
 * @returns Enable body.
 */
export function buildToolEnableBody(active: boolean): { active: boolean } {
  return { active };
}

/**
 * Build `{ target_role, permission }` only.
 *
 * @param input - Permission form. Extra keys are dropped.
 * @returns Permission body.
 */
export function buildToolPermissionBody(
  input: ToolPermissionRequest & Record<string, unknown>,
): ToolPermissionRequest {
  const targetRole = isInviteRole(String(input.target_role))
    ? input.target_role
    : "viewer";
  const permission = (TOOL_PERMISSIONS as readonly string[]).includes(
    String(input.permission),
  )
    ? (input.permission as ToolPermission)
    : "none";
  return { target_role: targetRole, permission };
}

/**
 * Return whether a glossary language is allow-listed.
 *
 * @param value - Candidate language.
 * @returns True for en|ar|mixed.
 */
export function isGlossaryLanguage(value: string): value is GlossaryLanguage {
  return (GLOSSARY_LANGUAGES as readonly string[]).includes(value);
}

/**
 * Build one glossary entry without SQL-like extras.
 *
 * @param input - Entry fields. `sql` and unknown keys are omitted.
 * @returns Entry, or null when `entry_key` fails the contract pattern.
 */
export function buildGlossaryEntry(
  input: GlossaryEntryRequest & Record<string, unknown>,
): GlossaryEntryRequest | null {
  const entryKey = String(input.entry_key ?? "");
  if (!ENTRY_KEY_RE.test(entryKey) || entryKey.length > 64) {
    return null;
  }
  const language = isGlossaryLanguage(String(input.language))
    ? input.language
    : "en";
  const entryType = (GLOSSARY_ENTRY_TYPES as readonly string[]).includes(
    String(input.entry_type),
  )
    ? (input.entry_type as GlossaryEntryType)
    : "canonical_term";
  const scope = (GLOSSARY_SCOPES as readonly string[]).includes(
    String(input.effective_scope),
  )
    ? (input.effective_scope as GlossaryScope)
    : "synthetic_eval";
  const aliasesRaw = Array.isArray(input.aliases) ? input.aliases : [];
  const aliases: GlossaryAliasRequest[] = aliasesRaw
    .slice(0, 20)
    .map((alias) => {
      const row = alias as GlossaryAliasRequest & Record<string, unknown>;
      return {
        alias: String(row.alias ?? ""),
        language: isGlossaryLanguage(String(row.language)) ? row.language : "en",
      };
    })
    .filter((alias) => alias.alias.length > 0);
  const entry: GlossaryEntryRequest = {
    entry_key: entryKey,
    canonical_term: String(input.canonical_term ?? ""),
    language,
    entry_type: entryType,
    effective_scope: scope,
  };
  if (typeof input.identifier_pattern === "string" && input.identifier_pattern) {
    entry.identifier_pattern = input.identifier_pattern;
  }
  if (typeof input.checksum_algorithm === "string" && input.checksum_algorithm) {
    entry.checksum_algorithm = input.checksum_algorithm;
  }
  if (aliases.length > 0) {
    entry.aliases = aliases;
  }
  return entry;
}

/**
 * Build a glossary import POST body. Extra SQL-like fields are omitted.
 *
 * @param input - Import form. Top-level `sql` is dropped.
 * @returns `{ source_name, source_version, idempotency_key, entries }`.
 */
export function buildGlossaryImportBody(
  input: ImportGlossaryRequest & Record<string, unknown>,
): ImportGlossaryRequest {
  const entries = (Array.isArray(input.entries) ? input.entries : [])
    .map((entry) =>
      buildGlossaryEntry(entry as GlossaryEntryRequest & Record<string, unknown>),
    )
    .filter((entry): entry is GlossaryEntryRequest => entry !== null)
    .slice(0, 500);
  return {
    source_name: String(input.source_name ?? ""),
    source_version: String(input.source_version ?? ""),
    idempotency_key: String(input.idempotency_key ?? ""),
    entries,
  };
}

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
