/**
 * Glossary import/approve/rollback and graph entity-rule curation.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { HandshakeBanner } from "./auth/auth-screens";
import { Button } from "./ui/button";
import { DataTable } from "./ui/data-table";
import { Input } from "./ui/input";
import { LimitationCallout } from "./ui/limitation-callout";
import { StatusBanner } from "./ui/status-banner";
import { StatusPill } from "./ui/status-pill";
import { CodeText, UserText } from "./ui/user-text";
import {
  approveEntityRule,
  approveGlossaryImport,
  fetchMe,
  importGlossary,
  listEntityRules,
  revokeEntityRule,
  rollbackGlossaryImport,
  upsertEntityRule,
  type ApiAuth,
} from "../lib/api";
import { useSession } from "../lib/auth/session-provider";
import { mutationFailureBanner } from "../lib/failure-copy";
import { sessionQueryKeys } from "../lib/query-keys";
import { showAdminMutationConvenience } from "../lib/roles";
import {
  GLOSSARY_ENTRY_TYPES,
  GLOSSARY_LANGUAGES,
  GLOSSARY_SCOPES,
  type EntityRuleListItem,
  type GlossaryEntryType,
  type GlossaryLanguage,
  type GlossaryScope,
} from "../lib/types";
import styles from "./developer-app.module.css";

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

/**
 * Curation surface for Hybrid glossary aliases and graph entity rules.
 *
 * @returns Curation panels.
 */
export function CurationApp() {
  const queryClient = useQueryClient();
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const [sourceName, setSourceName] = useState("sme-seed");
  const [sourceVersion, setSourceVersion] = useState("1");
  const [entryKey, setEntryKey] = useState("");
  const [canonicalTerm, setCanonicalTerm] = useState("");
  const [language, setLanguage] = useState<GlossaryLanguage>("en");
  const [entryType, setEntryType] = useState<GlossaryEntryType>("canonical_term");
  const [scope, setScope] = useState<GlossaryScope>("synthetic_eval");
  const [alias, setAlias] = useState("");
  const [importId, setImportId] = useState("");
  const [entityType, setEntityType] = useState("");
  const [canonicalName, setCanonicalName] = useState("");
  const [aliases, setAliases] = useState("");
  const [doNotMerge, setDoNotMerge] = useState("");
  const [outcome, setOutcome] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
            aliases: alias
              ? [{ alias, language }]
              : [],
          },
        ],
      });
    },
    onSuccess: (result) => {
      setError(null);
      setImportId(result.import_id);
      setOutcome(
        `glossary ${result.status} import_id=${result.import_id} entries=${String(result.entry_count)} aliases=${String(result.alias_count)}`,
      );
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

  const upsertMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return upsertEntityRule(auth, {
        entity_type: entityType,
        canonical_name: canonicalName,
        aliases: aliases
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        do_not_merge: doNotMerge
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        source: "admin",
        status: "approved",
      });
    },
    onSuccess: async (result) => {
      setError(null);
      setOutcome(
        `rule ${result.rule_id} ${result.status} row_version=${String(result.row_version)} invalidated=${String(result.invalidated)}`,
      );
      await queryClient.invalidateQueries({ queryKey: keys.entityRules });
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
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
      setOutcome(
        `approved ${result.rule_id} row_version=${String(result.row_version)}`,
      );
      await queryClient.invalidateQueries({ queryKey: keys.entityRules });
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
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
      setOutcome(
        `revoked ${result.rule_id} row_version=${String(result.row_version)}`,
      );
      await queryClient.invalidateQueries({ queryKey: keys.entityRules });
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const rules = rulesQuery.data?.rules ?? [];

  return (
    <div className={styles.shell}>
      <header className={styles.pageHeader}>
        <div>
          <h1>Curation</h1>
          <p className={styles.pageLead}>
            Glossary aliases and graph entity rules. Changes are limited to
            owners and admins.
          </p>
        </div>
      </header>
      <HandshakeBanner />
      {error ? (
        <StatusBanner kind="error" role="alert">
          {error}
        </StatusBanner>
      ) : null}
      {outcome ? (
        <StatusBanner kind="success" role="status">
          {outcome}
        </StatusBanner>
      ) : null}
      {!canMutate ? (
        <LimitationCallout tone="warning">
          Curation mutations are hidden for this role. Helpers still 403 on the
          server. There is no member glossary HTTP.
        </LimitationCallout>
      ) : null}

      {canMutate ? (
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
            <label>
              language
              <select
                value={language}
                onChange={(event) =>
                  setLanguage(event.target.value as GlossaryLanguage)
                }
              >
                {GLOSSARY_LANGUAGES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              entry_type
              <select
                value={entryType}
                onChange={(event) =>
                  setEntryType(event.target.value as GlossaryEntryType)
                }
              >
                {GLOSSARY_ENTRY_TYPES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label>
              effective_scope
              <select
                value={scope}
                onChange={(event) =>
                  setScope(event.target.value as GlossaryScope)
                }
              >
                {GLOSSARY_SCOPES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <Input
              label="alias (optional)"
              value={alias}
              onChange={(event) => setAlias(event.target.value)}
            />
          </div>
          <Button type="button" variant="primary" onClick={() => importMutation.mutate()}>
            Import glossary
          </Button>
          <Input
            label="import_id"
            value={importId}
            onChange={(event) => setImportId(event.target.value)}
          />
          <div className={styles.row}>
            <Button type="button" onClick={() => approveImportMutation.mutate()}>
              Approve import
            </Button>
            <Button type="button" onClick={() => rollbackImportMutation.mutate()}>
              Rollback import
            </Button>
          </div>
        </section>
      ) : null}

      {canMutate ? (
        <section className={styles.panel} aria-label="Entity rules">
          <h2>Entity rules</h2>
          <div className={styles.formGrid}>
            <Input
              label="entity_type"
              value={entityType}
              onChange={(event) => setEntityType(event.target.value)}
            />
            <Input
              label="canonical_name"
              value={canonicalName}
              onChange={(event) => setCanonicalName(event.target.value)}
            />
            <Input
              label="aliases (comma)"
              value={aliases}
              onChange={(event) => setAliases(event.target.value)}
            />
            <Input
              label="do_not_merge (comma)"
              value={doNotMerge}
              onChange={(event) => setDoNotMerge(event.target.value)}
            />
          </div>
          <Button type="button" onClick={() => upsertMutation.mutate()}>
            Upsert approved rule
          </Button>
          <DataTable
            caption="Entity rules"
            rows={rules}
            getRowId={(row) => row.id}
            columns={[
              {
                id: "canonical",
                header: "canonical_name",
                cell: (row) => <UserText value={row.canonical_name ?? ""} />,
              },
              {
                id: "type",
                header: "entity_type",
                cell: (row) => <UserText value={row.entity_type} />,
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
                id: "source",
                header: "source",
                cell: (row) => <UserText value={row.source} />,
              },
              {
                id: "version",
                header: "row_version",
                cell: (row) => <CodeText value={String(row.row_version)} />,
              },
              {
                id: "actions",
                header: "actions",
                cell: (row) => (
                  <div className={styles.row}>
                    <Button
                      type="button"
                      onClick={() => approveRuleMutation.mutate(row)}
                    >
                      Approve
                    </Button>
                    <Button
                      type="button"
                      onClick={() => revokeRuleMutation.mutate(row)}
                    >
                      Revoke
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </section>
      ) : null}
    </div>
  );
}
