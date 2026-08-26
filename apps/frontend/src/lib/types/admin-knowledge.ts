/**
 * Glossary and entity-rule OpenAPI types.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

export const GLOSSARY_LANGUAGES = ["en", "ar", "mixed"] as const;

export type GlossaryLanguage = (typeof GLOSSARY_LANGUAGES)[number];

/** Glossary entry types. */
export const GLOSSARY_ENTRY_TYPES = [
  "product_code",
  "project_name",
  "acronym",
  "canonical_term",
  "identifier_rule",
] as const;

export type GlossaryEntryType = (typeof GLOSSARY_ENTRY_TYPES)[number];

/** Glossary scopes. */
export const GLOSSARY_SCOPES = ["company", "synthetic_eval"] as const;

export type GlossaryScope = (typeof GLOSSARY_SCOPES)[number];

/** One alias in a glossary import. */
export type GlossaryAliasRequest = {
  alias: string;
  language: GlossaryLanguage;
};

/** One glossary entry. Extra SQL-like fields are forbidden. */
export type GlossaryEntryRequest = {
  entry_key: string;
  canonical_term: string;
  language: GlossaryLanguage;
  entry_type: GlossaryEntryType;
  effective_scope: GlossaryScope;
  identifier_pattern?: string | null;
  checksum_algorithm?: string | null;
  aliases?: GlossaryAliasRequest[];
};

/** `POST /admin/glossary/imports` body. Extra fields are forbidden. */
export type ImportGlossaryRequest = {
  source_name: string;
  source_version: string;
  idempotency_key: string;
  entries: GlossaryEntryRequest[];
};

/** Glossary import/approve/rollback identifiers. */
export type GlossaryImportResponse = {
  import_id: string;
  status: string;
  entry_count: number;
  alias_count: number;
};

/** Entity-rule lifecycle. */
export const ENTITY_RULE_STATUSES = ["suggested", "approved", "revoked"] as const;

export type EntityRuleStatus = (typeof ENTITY_RULE_STATUSES)[number];

/** Entity-rule provenance. */
export const ENTITY_RULE_SOURCES = ["admin", "feedback", "model"] as const;

export type EntityRuleSource = (typeof ENTITY_RULE_SOURCES)[number];

/** `GET /admin/graph/entity-rules` item. */
export type EntityRuleListItem = {
  id: string;
  entity_type: string;
  canonical_name: string | null;
  display_label: string | null;
  aliases: string[];
  do_not_merge: string[];
  languages: string[];
  alias_scope: string;
  relation_label_policy: string;
  status: EntityRuleStatus;
  active: boolean;
  row_version: number;
  source: EntityRuleSource;
  reason: string;
  confidence: number | null;
  created_at: string | null;
  updated_at: string | null;
};

/** `GET /admin/graph/entity-rules` envelope. */
export type EntityRuleListResponse = {
  rules: EntityRuleListItem[];
};

/** Approve/revoke concurrency body. Extra fields are forbidden. */
export type EntityRuleConcurrencyRequest = {
  row_version: number;
};

/** Entity-rule mutation identifiers. Alias text is omitted. */
export type EntityRuleMutationResponse = {
  rule_id: string;
  status: EntityRuleStatus;
  row_version: number;
  entity_rules_generation: number;
  rebuild_job_id: string | null;
  repair_job_id: string | null;
  invalidated: boolean;
};

/** `POST /admin/graph/entity-rules` upsert. Extra fields are forbidden. */
export type EntityRuleUpsertRequest = {
  entity_type: string;
  canonical_name: string;
  aliases?: string[];
  do_not_merge?: string[];
  display_label?: string | null;
  languages?: string[];
  alias_scope?: "company" | "synthetic_eval";
  relation_label_policy?: "directed" | "symmetric";
  reason?: string;
  source?: EntityRuleSource;
  confidence?: number | null;
  status?: EntityRuleStatus;
  row_version?: number | null;
};

/** `POST /admin/graph/entity-rules/suggestions`. Never auto-approves. */
export type EntityRuleSuggestRequest = {
  entity_type: string;
  canonical_name: string;
  aliases?: string[];
  do_not_merge?: string[];
  display_label?: string | null;
  languages?: string[];
  alias_scope?: "company" | "synthetic_eval";
  relation_label_policy?: "directed" | "symmetric";
  reason?: string;
  source?: EntityRuleSource;
  confidence?: number | null;
};
