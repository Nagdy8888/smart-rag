/**
 * Glossary import, approve, and rollback form.
 */

"use client";

import { useState } from "react";
import { Button, PrimaryAction } from "../ui/button";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import type { UseCurationMutationsResult } from "./hooks/use-curation-mutations";
import {
  GLOSSARY_ENTRY_TYPES,
  GLOSSARY_LANGUAGES,
  GLOSSARY_SCOPES,
  type GlossaryEntryType,
  type GlossaryLanguage,
  type GlossaryScope,
} from "../../lib/types";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

const LANGUAGE_OPTIONS = GLOSSARY_LANGUAGES.map((item) => ({
  value: item,
  label: item,
}));
const ENTRY_TYPE_OPTIONS = GLOSSARY_ENTRY_TYPES.map((item) => ({
  value: item,
  label: item,
}));
const SCOPE_OPTIONS = GLOSSARY_SCOPES.map((item) => ({
  value: item,
  label: item,
}));

export type GlossaryPanelProps = {
  /** Shared curation mutation controller. */
  curation: UseCurationMutationsResult;
};

/**
 * Render glossary import controls.
 *
 * @param props - Shared mutation controller.
 * @returns Glossary section. Does not authorize mutations.
 */
export function GlossaryPanel({ curation }: GlossaryPanelProps) {
  const [sourceName, setSourceName] = useState("sme-seed");
  const [sourceVersion, setSourceVersion] = useState("1");
  const [entryKey, setEntryKey] = useState("");
  const [canonicalTerm, setCanonicalTerm] = useState("");
  const [language, setLanguage] = useState<GlossaryLanguage>("en");
  const [entryType, setEntryType] = useState<GlossaryEntryType>("canonical_term");
  const [scope, setScope] = useState<GlossaryScope>("synthetic_eval");
  const [alias, setAlias] = useState("");

  return (
    <section className={styles.panel} aria-label="Glossary import">
      <h2>Glossary import</h2>
      <div className={styles.formGrid}>
        <Input
          label="source_name"
          value={sourceName}
          onChange={(event) => setSourceName(event.target.value)}
        />
        <Input
          label="source_version"
          value={sourceVersion}
          onChange={(event) => setSourceVersion(event.target.value)}
        />
        <Input
          label="entry_key"
          value={entryKey}
          onChange={(event) => setEntryKey(event.target.value)}
        />
        <Input
          label="canonical_term"
          value={canonicalTerm}
          onChange={(event) => setCanonicalTerm(event.target.value)}
        />
        <Select
          label="language"
          value={language}
          options={LANGUAGE_OPTIONS}
          onChange={(event) => setLanguage(event.target.value as GlossaryLanguage)}
        />
        <Select
          label="entry_type"
          value={entryType}
          options={ENTRY_TYPE_OPTIONS}
          onChange={(event) => setEntryType(event.target.value as GlossaryEntryType)}
        />
        <Select
          label="effective_scope"
          value={scope}
          options={SCOPE_OPTIONS}
          onChange={(event) => setScope(event.target.value as GlossaryScope)}
        />
        <Input
          label="alias (optional)"
          value={alias}
          onChange={(event) => setAlias(event.target.value)}
        />
      </div>
      <PrimaryAction
        type="button"
        data-action-id="admin.glossary.import"
        pending={curation.importPending}
        pendingLabel="Importing…"
        onClick={() =>
          curation.importGlossary({
            sourceName,
            sourceVersion,
            entryKey,
            canonicalTerm,
            language,
            entryType,
            scope,
            alias,
          })
        }
      >
        Import glossary
      </PrimaryAction>
      <p className={styles.muted}>
        Status: {curation.outcome ?? "none"} import_id {curation.importId || "—"}
      </p>
      <Input
        label="import_id"
        value={curation.importId}
        onChange={(event) => curation.setImportId(event.target.value)}
      />
      <div className={styles.row}>
        <Button
          type="button"
          data-action-id="admin.glossary.approve"
          pending={curation.approveImportPending}
          pendingLabel="Approving…"
          onClick={curation.approveImport}
        >
          Approve
        </Button>
        <Button
          type="button"
          data-action-id="admin.glossary.rollback"
          pending={curation.rollbackPending}
          pendingLabel="Rolling back…"
          onClick={curation.rollbackImport}
        >
          Rollback
        </Button>
      </div>
    </section>
  );
}
