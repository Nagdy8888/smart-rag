/**
 * Glossary and entity-rule mutations. Server authorization remains authoritative.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  approveEntityRule,
  approveGlossaryImport,
  importGlossary,
  listEntityRules,
  patchEntityRule,
  revokeEntityRule,
  rollbackGlossaryImport,
  suggestEntityRule,
  type ApiAuth,
} from "../../../lib/api";
import { useApiAuth } from "../../../lib/auth/use-api-auth";
import { useSession } from "../../../lib/auth/session-provider";
import { mutationFailureBanner } from "../../../lib/failure-copy";
import { useCurrentUser } from "../../../lib/hooks/use-current-user";
import { newIdempotencyKey } from "../../../lib/idempotency";
import { sessionQueryKeys } from "../../../lib/query-keys";
import { showAdminMutationConvenience } from "../../../lib/roles";
import type { EntityRuleListItem } from "../../../lib/types";
import type { EntityRuleDraftFields, GlossaryImportFields } from "./curation-fields";

export type { EntityRuleDraftFields, GlossaryImportFields } from "./curation-fields";

/**
 * Own the seven curation mutations, stale-row conflict, and scoped invalidation.
 *
 * Approve still posts `{ row_version }` only. One idempotency key is minted
 * per import attempt, not inside a retry of that attempt.
 *
 * @returns Mutation handles, banners, and permission convenience flags.
 */
export function useCurationMutations() {
  const queryClient = useQueryClient();
  const session = useSession();
  const auth = useApiAuth();
  const keys = sessionQueryKeys(session.accessToken);
  const { currentUser, isFetched } = useCurrentUser();
  const [importId, setImportId] = useState("");
  const [outcome, setOutcome] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [staleConflict, setStaleConflict] = useState(false);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [editRule, setEditRule] = useState<EntityRuleListItem | null>(null);

  const canMutate = showAdminMutationConvenience(currentUser?.role);
  const rulesQuery = useQuery({
    queryKey: keys.entityRules,
    queryFn: () => listEntityRules(auth as ApiAuth),
    enabled: auth !== null && canMutate,
  });

  const importMutation = useMutation({
    mutationFn: async (fields: GlossaryImportFields) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return importGlossary(auth, {
        source_name: fields.sourceName,
        source_version: fields.sourceVersion,
        idempotency_key: newIdempotencyKey(),
        entries: [
          {
            entry_key: fields.entryKey,
            canonical_term: fields.canonicalTerm,
            language: fields.language,
            entry_type: fields.entryType,
            effective_scope: fields.scope,
            aliases: fields.alias ? [{ alias: fields.alias, language: fields.language }] : [],
          },
        ],
      });
    },
    onSuccess: (result) => {
      setError(null);
      setImportId(result.import_id);
      setOutcome(`Glossary import ${result.status}.`);
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const approveImportMutation = useMutation({
    mutationFn: async (id: string) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return approveGlossaryImport(auth, id.trim());
    },
    onSuccess: (result) => {
      setError(null);
      setOutcome(`Glossary import ${result.status}.`);
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const rollbackImportMutation = useMutation({
    mutationFn: async (id: string) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return rollbackGlossaryImport(auth, id.trim());
    },
    onSuccess: (result) => {
      setError(null);
      setOutcome(`Glossary import ${result.status}.`);
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const suggestMutation = useMutation({
    mutationFn: async (fields: EntityRuleDraftFields) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return suggestEntityRule(auth, {
        entity_type: fields.entityType,
        canonical_name: fields.canonicalName,
        aliases: fields.aliases.split(",").map((item) => item.trim()).filter(Boolean),
        source: "feedback",
      });
    },
    onSuccess: async () => {
      setError(null);
      setStaleConflict(false);
      setSuggestOpen(false);
      setOutcome("Suggestion saved.");
      await queryClient.invalidateQueries({ queryKey: keys.entityRules });
    },
    onError: (caught: Error) => setError(mutationFailureBanner(caught)),
  });

  const patchMutation = useMutation({
    mutationFn: async ({
      rule,
      fields,
    }: {
      rule: EntityRuleListItem;
      fields: EntityRuleDraftFields;
    }) => {
      if (auth === null) {
        throw new Error("signed_out");
      }
      return patchEntityRule(auth, rule.id, {
        entity_type: fields.entityType || rule.entity_type,
        canonical_name: fields.canonicalName || rule.canonical_name || "",
        aliases: fields.aliases
          ? fields.aliases.split(",").map((item) => item.trim()).filter(Boolean)
          : rule.aliases,
        row_version: rule.row_version,
      });
    },
    onSuccess: async () => {
      setError(null);
      setStaleConflict(false);
      setEditRule(null);
      setOutcome("Rule saved.");
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
    onSuccess: async () => {
      setError(null);
      setStaleConflict(false);
      setOutcome("Rule approved.");
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
    onSuccess: async () => {
      setError(null);
      setStaleConflict(false);
      setOutcome("Rule revoked.");
      await queryClient.invalidateQueries({ queryKey: keys.entityRules });
    },
    onError: (caught: Error) => {
      setStaleConflict(caught.message === "stale_row_version");
      setError(mutationFailureBanner(caught));
    },
  });

  return {
    canMutate,
    meFetched: isFetched,
    importId,
    setImportId,
    outcome,
    error,
    staleConflict,
    suggestOpen,
    setSuggestOpen,
    editRule,
    setEditRule,
    rules: rulesQuery.data?.rules ?? [],
    importPending: importMutation.isPending,
    approveImportPending: approveImportMutation.isPending,
    rollbackPending: rollbackImportMutation.isPending,
    suggestPending: suggestMutation.isPending,
    patchPending: patchMutation.isPending,
    approveRulePending: approveRuleMutation.isPending,
    revokePending: revokeRuleMutation.isPending,
    importGlossary: (fields: GlossaryImportFields) => importMutation.mutate(fields),
    approveImport: () => approveImportMutation.mutate(importId),
    rollbackImport: () => rollbackImportMutation.mutate(importId),
    suggestRule: (fields: EntityRuleDraftFields) => suggestMutation.mutate(fields),
    patchRule: (rule: EntityRuleListItem, fields: EntityRuleDraftFields) =>
      patchMutation.mutate({ rule, fields }),
    approveRule: (rule: EntityRuleListItem) => approveRuleMutation.mutate(rule),
    revokeRule: (rule: EntityRuleListItem) => revokeRuleMutation.mutate(rule),
    reloadRules: () => {
      setStaleConflict(false);
      void queryClient.invalidateQueries({ queryKey: keys.entityRules });
    },
  };
}

/** Controller returned by `useCurationMutations`. */
export type UseCurationMutationsResult = ReturnType<typeof useCurationMutations>;
