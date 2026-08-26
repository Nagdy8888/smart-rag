/**
 * Entity-rule suggest, patch, approve, and revoke table.
 */

"use client";

import { useState } from "react";
import { Button, PrimaryAction } from "../ui/button";
import { DataTable } from "../ui/data-table";
import { Input } from "../ui/input";
import { Menu } from "../ui/menu";
import { StatusPill } from "../ui/status-pill";
import { CodeText, UserText } from "../ui/user-text";
import type { UseCurationMutationsResult } from "./hooks/use-curation-mutations";
import type { EntityRuleListItem } from "../../lib/types";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

export type EntityRulesPanelProps = {
  /** Shared curation mutation controller. */
  curation: UseCurationMutationsResult;
};

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
      <DataTable
        caption="Entity rules"
        rows={curation.rules}
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
    </section>
  );
}
