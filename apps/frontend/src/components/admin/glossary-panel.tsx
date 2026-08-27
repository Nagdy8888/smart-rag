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
  GLOSSARY_SCOPES,
  type GlossaryEntryType,
  type GlossaryLanguage,
  type GlossaryScope,
} from "../../lib/types";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

const LANGUAGE_OPTIONS: { value: GlossaryLanguage; label: string }[] = [
  { value: "en", label: "English" },
  { value: "ar", label: "Arabic" },
  { value: "mixed", label: "Mixed" },
];
const ENTRY_TYPE_OPTIONS = GLOSSARY_ENTRY_TYPES.map((item) => ({
  value: item,
  label: item.replaceAll("_", " "),
}));
const SCOPE_OPTIONS = GLOSSARY_SCOPES.map((item) => ({
  value: item,
  label: item === "synthetic_eval" ? "Evaluation only" : "Company",
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
  const [sourceName, setSourceName] = useState("manual");
  const [sourceVersion, setSourceVersion] = useState("1");
  const [entryKey, setEntryKey] = useState("");
  const [canonicalTerm, setCanonicalTerm] = useState("");
  const [language, setLanguage] = useState<GlossaryLanguage>("en");
  const [entryType, setEntryType] = useState<GlossaryEntryType>("canonical_term");
  const [scope, setScope] = useState<GlossaryScope>("company");
  const [alias, setAlias] = useState("");

  return (
    <section className={styles.panel} aria-label="Word aliases">
      <h2>Word aliases</h2>
      <p className={styles.panelLead}>
        Add a company term and optional nickname, then approve it so questions
        using either wording still find the right documents. Rollback removes
        that import from search. Entry keys may use letters, numbers, dots,
        underscores, colons, or hyphens.
      </p>
      <div className={styles.formGrid}>
        <Input
          label="Source name"
          value={sourceName}
          onChange={(event) => setSourceName(event.target.value)}
        />
        <Input
          label="Source version"
          value={sourceVersion}
          onChange={(event) => setSourceVersion(event.target.value)}
        />
        <Input
          label="Entry key"
          value={entryKey}
          onChange={(event) => setEntryKey(event.target.value)}
        />
        <Input
          label="Canonical term"
          value={canonicalTerm}
          onChange={(event) => setCanonicalTerm(event.target.value)}
        />
        <Select
          label="Language"
          value={language}
          options={LANGUAGE_OPTIONS}
          onChange={(event) => setLanguage(event.target.value as GlossaryLanguage)}
        />
        <Select
          label="Entry type"
          value={entryType}
          options={ENTRY_TYPE_OPTIONS}
          onChange={(event) => setEntryType(event.target.value as GlossaryEntryType)}
        />
        <Select
          label="Scope"
          value={scope}
          options={SCOPE_OPTIONS}
          onChange={(event) => setScope(event.target.value as GlossaryScope)}
        />
        <Input
          label="Alias (optional)"
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
      <Input
        label="Import ID"
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
