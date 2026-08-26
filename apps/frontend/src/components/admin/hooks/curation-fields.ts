/**
 * Curation form field bags passed into mutation handlers.
 */

import type {
  GlossaryEntryType,
  GlossaryLanguage,
  GlossaryScope,
} from "../../../lib/types";

/** Glossary import form values. */
export type GlossaryImportFields = {
  sourceName: string;
  sourceVersion: string;
  entryKey: string;
  canonicalTerm: string;
  language: GlossaryLanguage;
  entryType: GlossaryEntryType;
  scope: GlossaryScope;
  alias: string;
};

/** Entity-rule suggest/edit draft. */
export type EntityRuleDraftFields = {
  entityType: string;
  canonicalName: string;
  aliases: string;
};
