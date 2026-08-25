/**
 * Glossary import/approve/rollback and entity-rule PATCH, suggest, approve, revoke.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Button, PrimaryAction } from "../ui/button";
import { DataTable } from "../ui/data-table";
import { Input } from "../ui/input";
import { Menu } from "../ui/menu";
import { Select } from "../ui/select";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import { CodeText, UserText } from "../ui/user-text";
import {
  approveEntityRule,
  approveGlossaryImport,
  fetchMe,
  importGlossary,
  listEntityRules,
  patchEntityRule,
  revokeEntityRule,
  rollbackGlossaryImport,
  suggestEntityRule,
  type ApiAuth,
} from "../../lib/api";
import { STALE_ROW_VERSION_COPY } from "../../lib/admin-copy";
import { useSession } from "../../lib/auth/session-provider";
import { mutationFailureBanner } from "../../lib/failure-copy";
import { sessionQueryKeys } from "../../lib/query-keys";
import { showAdminMutationConvenience } from "../../lib/roles";
import {
  GLOSSARY_ENTRY_TYPES,
  GLOSSARY_LANGUAGES,
  GLOSSARY_SCOPES,
  type EntityRuleListItem,
  type GlossaryEntryType,
  type GlossaryLanguage,
  type GlossaryScope,
} from "../../lib/types";
import styles from "./admin.module.css";

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

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

/**
 * Curation tab with Glossary and Entity rules.
 *
 * @returns Nested tabs. Approve still posts `{ row_version }` only.
 */
export function CurationPanel() {
  const queryClient = useQueryClient();
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const [inner, setInner] = useState<"glossary" | "rules">("glossary");
  const [sourceName, setSourceName] = useState("sme-seed");
  const [sourceVersion, setSourceVersion] = useState("1");
  const [entryKey, setEntryKey] = useState("");
  const [canonicalTerm, setCanonicalTerm] = useState("");
  const [language, setLanguage] = useState<GlossaryLanguage>("en");
  const [entryType, setEntryType] = useState<GlossaryEntryType>("canonical_term");
  const [scope, setScope] = useState<GlossaryScope>("synthetic_eval");
  const [alias, setAlias] = useState("");
  const [importId, setImportId] = useState("");
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [editRule, setEditRule] = useState<EntityRuleListItem | null>(null);
  const [entityType, setEntityType] = useState("");
  const [canonicalName, setCanonicalName] = useState("");
  const [aliases, setAliases] = useState("");
  const [outcome, setOutcome] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [staleConflict, setStaleConflict] = useState(false);

  const meQuery = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });
  const canMutate = showAdminMutationConvenience(meQuery.data?.role);
  const rulesQuery = useQuery({
    queryKey: keys.entityRules,
    queryFn: () => listEntityRules(auth as ApiAuth),
    enabled: auth !== null && canMutate,
  });

  const importMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return importGlossary(auth, {
        source_name: sourceName,
        source_version: sourceVersion,
        idempotency_key: newIdempotencyKey(),
        entries: [
          {
            entry_key: entryKey,
            canonical_term: canonicalTerm,
            language,
            entry_type: entryType,
            effective_scope: scope,
            aliases: alias ? [{ alias, language }] : [],
          },
        ],
      });
    },
    onSuccess: (result) => {
      setError(null);
      setImportId(result.import_id);
      setOutcome(`glossary ${result.status} import_id=${result.import_id}`);
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const approveImportMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return approveGlossaryImport(auth, importId.trim());
    },
    onSuccess: (result) => {
      setError(null);
      setOutcome(`glossary ${result.status} import_id=${result.import_id}`);
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const rollbackImportMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return rollbackGlossaryImport(auth, importId.trim());
    },
    onSuccess: (result) => {
      setError(null);
      setOutcome(`glossary ${result.status} import_id=${result.import_id}`);
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const suggestMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return suggestEntityRule(auth, {
        entity_type: entityType,
        canonical_name: canonicalName,
        aliases: aliases.split(",").map((item) => item.trim()).filter(Boolean),
        source: "feedback",
      });
    },
    onSuccess: async (result) => {
      setError(null);
      setStaleConflict(false);
      setSuggestOpen(false);
      setOutcome(`suggested ${result.rule_id} row_version=${String(result.row_version)}`);
      await queryClient.invalidateQueries({ queryKey: keys.entityRules });
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const patchMutation = useMutation({
    mutationFn: async (rule: EntityRuleListItem) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return patchEntityRule(auth, rule.id, {
        entity_type: entityType || rule.entity_type,
        canonical_name: canonicalName || rule.canonical_name || "",
        aliases: aliases
          ? aliases.split(",").map((item) => item.trim()).filter(Boolean)
          : rule.aliases,
        row_version: rule.row_version,
      });
    },
    onSuccess: async (result) => {
      setError(null);
      setStaleConflict(false);
      setEditRule(null);
      setOutcome(`patched ${result.rule_id} row_version=${String(result.row_version)}`);
      await queryClient.invalidateQueries({ queryKey: keys.entityRules });
    },
    onError: (caught: Error) => {
      setStaleConflict(caught.message === "stale_row_version");
      setError(mutationFailureBanner(caught));
    },
  });

  const approveRuleMutation = useMutation({
    mutationFn: async (rule: EntityRuleListItem) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return approveEntityRule(auth, rule.id, rule.row_version);
    },
    onSuccess: async (result) => {
      setError(null);
      setStaleConflict(false);
      setOutcome(`approved ${result.rule_id} row_version=${String(result.row_version)}`);
      await queryClient.invalidateQueries({ queryKey: keys.entityRules });
    },
    onError: (caught: Error) => {
      setStaleConflict(caught.message === "stale_row_version");
      setError(mutationFailureBanner(caught));
    },
  });

  const revokeRuleMutation = useMutation({
    mutationFn: async (rule: EntityRuleListItem) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return revokeEntityRule(auth, rule.id, rule.row_version);
    },
    onSuccess: async (result) => {
      setError(null);
      setStaleConflict(false);
      setOutcome(`revoked ${result.rule_id} row_version=${String(result.row_version)}`);
      await queryClient.invalidateQueries({ queryKey: keys.entityRules });
    },
    onError: (caught: Error) => {
      setStaleConflict(caught.message === "stale_row_version");
      setError(mutationFailureBanner(caught));
    },
  });

  const rules = rulesQuery.data?.rules ?? [];

  if (!canMutate && meQuery.isFetched) {
    return (
      <p className={styles.muted}>
        Curation mutations are hidden for this role. Helpers still 403 on the server.
      </p>
    );
  }

  return (
    <div className={styles.stack}>
      {error ? (
        <StatusBanner kind="error" role="alert">
          {error}
        </StatusBanner>
      ) : null}
      {staleConflict ? (
        <StatusBanner kind="warning" role="alert">
          {STALE_ROW_VERSION_COPY}{" "}
          <Button
            type="button"
            data-action-id="admin.entity_rule.reload"
            onClick={() => {
              setStaleConflict(false);
              void queryClient.invalidateQueries({ queryKey: keys.entityRules });
            }}
          >
            Reload rule
          </Button>
        </StatusBanner>
      ) : null}
      {outcome ? (
        <StatusBanner kind="success" role="status">
          {outcome}
        </StatusBanner>
      ) : null}

      <div role="tablist" aria-label="Curation sections" className={styles.tabList}>
        <button
          type="button"
          role="tab"
          aria-selected={inner === "glossary"}
          className={inner === "glossary" ? styles.tabCurrent : styles.tab}
          data-action-id="admin.curation.glossary"
          onClick={() => setInner("glossary")}
        >
          Glossary
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={inner === "rules"}
          className={inner === "rules" ? styles.tabCurrent : styles.tab}
          data-action-id="admin.curation.rules"
          onClick={() => setInner("rules")}
        >
          Entity rules
        </button>
      </div>

      {inner === "glossary" ? (
        <section className={styles.panel} aria-label="Glossary import">
          <h2>Glossary import</h2>
          <div className={styles.formGrid}>
            <Input label="source_name" value={sourceName} onChange={(event) => setSourceName(event.target.value)} />
            <Input label="source_version" value={sourceVersion} onChange={(event) => setSourceVersion(event.target.value)} />
            <Input label="entry_key" value={entryKey} onChange={(event) => setEntryKey(event.target.value)} />
            <Input label="canonical_term" value={canonicalTerm} onChange={(event) => setCanonicalTerm(event.target.value)} />
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
            <Input label="alias (optional)" value={alias} onChange={(event) => setAlias(event.target.value)} />
          </div>
          <PrimaryAction
            type="button"
            data-action-id="admin.glossary.import"
            pending={importMutation.isPending}
            pendingLabel="Importing…"
            onClick={() => importMutation.mutate()}
          >
            Import glossary
          </PrimaryAction>
          <p className={styles.muted}>
            Status: {outcome ?? "none"} import_id {importId || "—"}
          </p>
          <Input label="import_id" value={importId} onChange={(event) => setImportId(event.target.value)} />
          <div className={styles.row}>
            <Button
              type="button"
              data-action-id="admin.glossary.approve"
              onClick={() => approveImportMutation.mutate()}
            >
              Approve
            </Button>
            <Button
              type="button"
              data-action-id="admin.glossary.rollback"
              onClick={() => rollbackImportMutation.mutate()}
            >
              Rollback
            </Button>
          </div>
        </section>
      ) : (
        <section className={styles.panel} aria-label="Entity rules">
          <div className={styles.row}>
            <h2>Entity rules</h2>
            <Button
              type="button"
              data-action-id="admin.entity_rule.suggest"
              onClick={() => setSuggestOpen(true)}
            >
              Suggest rule
            </Button>
          </div>
          {suggestOpen || editRule ? (
            <div className={styles.formGrid}>
              <Input label="entity_type" value={entityType} onChange={(event) => setEntityType(event.target.value)} />
              <Input label="canonical_name" value={canonicalName} onChange={(event) => setCanonicalName(event.target.value)} />
              <Input label="aliases (comma)" value={aliases} onChange={(event) => setAliases(event.target.value)} />
            </div>
          ) : null}
          {suggestOpen ? (
            <PrimaryAction
              type="button"
              data-action-id="admin.entity_rule.suggest"
              pending={suggestMutation.isPending}
              pendingLabel="Suggesting…"
              onClick={() => suggestMutation.mutate()}
            >
              Submit suggestion
            </PrimaryAction>
          ) : null}
          {editRule ? (
            <PrimaryAction
              type="button"
              data-action-id="admin.entity_rule.edit"
              pending={patchMutation.isPending}
              pendingLabel="Saving…"
              onClick={() => patchMutation.mutate(editRule)}
            >
              Save rule
            </PrimaryAction>
          ) : null}
          <DataTable
            caption="Entity rules"
            rows={rules}
            getRowId={(row) => row.id}
            columns={[
              {
                id: "type",
                header: "canonical type",
                cell: (row) => <UserText value={row.entity_type} />,
              },
              {
                id: "canonical",
                header: "canonical name",
                cell: (row) => <UserText value={row.canonical_name ?? ""} />,
              },
              {
                id: "aliases",
                header: "aliases",
                cell: (row) => <UserText value={row.aliases.join(", ")} />,
              },
              {
                id: "status",
                header: "status",
                cell: (row) => (
                  <StatusPill
                    tone={row.status === "approved" ? "success" : "neutral"}
                    status={row.status}
                  />
                ),
              },
              {
                id: "version",
                header: "row version",
                cell: (row) => <CodeText value={String(row.row_version)} />,
              },
              {
                id: "actions",
                header: "actions",
                cell: (row) => (
                  <Menu
                    label="Rule actions"
                    trigger={<span>Actions</span>}
                    items={[
                      {
                        id: "edit",
                        label: "Edit",
                        actionId: "admin.entity_rule.edit",
                        onSelect: () => {
                          setEditRule(row);
                          setSuggestOpen(false);
                          setEntityType(row.entity_type);
                          setCanonicalName(row.canonical_name ?? "");
                          setAliases(row.aliases.join(", "));
                        },
                      },
                      {
                        id: "approve",
                        label: "Approve",
                        actionId: "admin.entity_rule.approve",
                        onSelect: () => approveRuleMutation.mutate(row),
                      },
                      {
                        id: "revoke",
                        label: "Revoke",
                        danger: true,
                        actionId: "admin.entity_rule.revoke",
                        onSelect: () => revokeRuleMutation.mutate(row),
                      },
                    ]}
                  />
                ),
              },
            ]}
          />
        </section>
      )}
    </div>
  );
}
