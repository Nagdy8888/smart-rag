/**
 * Extra-forbid glossary import and entry POST bodies.
 */

import {
  GLOSSARY_ENTRY_TYPES,
  GLOSSARY_LANGUAGES,
  GLOSSARY_SCOPES,
  type GlossaryAliasRequest,
  type GlossaryEntryRequest,
  type GlossaryEntryType,
  type GlossaryLanguage,
  type GlossaryScope,
  type ImportGlossaryRequest,
} from "../types";

const ENTRY_KEY_RE = /^[A-Za-z0-9._:-]+$/;

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
