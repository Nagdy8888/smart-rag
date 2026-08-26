/**
 * Extra-forbid builders for administration POST bodies.
 *
 * SQL-like and unknown fields are omitted even when callers pass them.
 */

export {
  buildInvitationCreateBody,
  buildToolEnableBody,
  buildToolPermissionBody,
  buildToolSeedBody,
  isInviteRole,
} from "./admin-bodies/invitations-tools";
export {
  buildGlossaryEntry,
  buildGlossaryImportBody,
  isGlossaryLanguage,
} from "./admin-bodies/glossary";
export {
  buildEntityRuleConcurrencyBody,
  buildEntityRuleSuggestBody,
  buildEntityRuleUpsertBody,
} from "./admin-bodies/entity-rules";
