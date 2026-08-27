/**
 * Entity-rule suggest, patch, approve, and revoke table.
 */

"use client";

import { useState } from "react";
import { Button, PrimaryAction } from "../ui/button";
import { DataTable } from "../ui/data-table";
import { EmptyState } from "../ui/empty-state";
import { Input } from "../ui/input";
import { Menu } from "../ui/menu";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import type { UseCurationMutationsResult } from "./hooks/use-curation-mutations";
import type { EntityRuleListItem, EntityRuleStatus } from "../../lib/types";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

export type EntityRulesPanelProps = {
  /** Shared curation mutation controller. */
  curation: UseCurationMutationsResult;
};

/**
 * Map a rule status to pill copy and tone.
 *
 * @param status - Server status.
 * @returns Display label and tone.
 */
function ruleStatusPill(status: EntityRuleStatus | string): {
  label: string;
  tone: "success" | "neutral" | "warning";
} {
  if (status === "approved") {
    return { label: "Approved", tone: "success" };
  }
  if (status === "revoked") {
    return { label: "Revoked", tone: "warning" };
  }
  return { label: "Suggested", tone: "neutral" };
}

/**
 * Render entity-rule drafting and the authorized rule table.
 *
 * @param props - Shared mutation controller.
 * @returns Entity rules section. Approve still posts `{ row_version }` only.
 */
export function EntityRulesPanel({ curation }: EntityRulesPanelProps) {
  const [entityType, setEntityType] = useState("");
  const [canonicalName, setCanonicalName] = useState("");
  const [aliases, setAliases] = useState("");
  const draft = { entityType, canonicalName, aliases };

  /**
   * Open the edit form for one rule and close suggest.
   *
   * @param row - Authorized rule row.
   */
  function startEdit(row: EntityRuleListItem): void {
    curation.setEditRule(row);
    curation.setSuggestOpen(false);
    setEntityType(row.entity_type);
    setCanonicalName(row.canonical_name ?? "");
    setAliases(row.aliases.join(", "));
  }

  return (
    <section className={styles.panel} aria-label="Entity rules">
      <div className={styles.row}>
        <h2>Entity rules</h2>
        <Button
          type="button"
          data-action-id="admin.entity_rule.suggest"
          onClick={() => curation.setSuggestOpen(true)}
        >
          Suggest rule
        </Button>
      </div>
      {curation.suggestOpen || curation.editRule ? (
        <div className={styles.formGrid}>
          <Input
            label="Entity type"
            value={entityType}
            onChange={(event) => setEntityType(event.target.value)}
          />
          <Input
            label="Canonical name"
            value={canonicalName}
            onChange={(event) => setCanonicalName(event.target.value)}
          />
          <Input
            label="Aliases"
            value={aliases}
            onChange={(event) => setAliases(event.target.value)}
          />
        </div>
      ) : null}
      {curation.suggestOpen ? (
        <PrimaryAction
          type="button"
          data-action-id="admin.entity_rule.suggest"
          pending={curation.suggestPending}
          pendingLabel="Suggesting…"
          onClick={() => curation.suggestRule(draft)}
        >
          Submit suggestion
        </PrimaryAction>
      ) : null}
      {curation.editRule ? (
        <PrimaryAction
          type="button"
          data-action-id="admin.entity_rule.edit"
          pending={curation.patchPending}
          pendingLabel="Saving…"
          onClick={() => {
            if (curation.editRule) {
              curation.patchRule(curation.editRule, draft);
            }
          }}
        >
          Save rule
        </PrimaryAction>
      ) : null}
      {curation.rules.length === 0 ? (
        <EmptyState
          title="No entity rules yet."
          body="Suggest a rule to keep aliases and display names consistent."
          icon="curation"
        />
      ) : (
        <DataTable
          caption="Entity rules"
          rows={curation.rules}
          getRowId={(row) => row.id}
          columns={[
            {
              id: "type",
              header: "Type",
              cell: (row) => <UserText value={row.entity_type} />,
            },
            {
              id: "canonical",
              header: "Canonical name",
              cell: (row) => <UserText value={row.canonical_name ?? ""} />,
            },
            {
              id: "aliases",
              header: "Aliases",
              cell: (row) => <UserText value={row.aliases.join(", ")} />,
            },
            {
              id: "status",
              header: "Status",
              cell: (row) => {
                const pill = ruleStatusPill(row.status);
                return <StatusPill tone={pill.tone} status={pill.label} />;
              },
            },
            {
              id: "actions",
              header: "Actions",
              cell: (row) => (
                <Menu
                  label="Rule actions"
                  trigger={<span>Actions</span>}
                  items={[
                    {
                      id: "edit",
                      label: "Edit",
                      actionId: "admin.entity_rule.edit",
                      onSelect: () => startEdit(row),
                    },
                    {
                      id: "approve",
                      label: curation.approveRulePending ? "Approving…" : "Approve",
                      disabled: curation.approveRulePending,
                      actionId: "admin.entity_rule.approve",
                      onSelect: () => curation.approveRule(row),
                    },
                    {
                      id: "revoke",
                      label: curation.revokePending ? "Revoking…" : "Revoke",
                      danger: true,
                      disabled: curation.revokePending,
                      actionId: "admin.entity_rule.revoke",
                      onSelect: () => curation.revokeRule(row),
                    },
                  ]}
                />
              ),
            },
          ]}
        />
      )}
    </section>
  );
}
