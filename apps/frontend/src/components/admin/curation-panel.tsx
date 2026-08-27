/**
 * Glossary import/approve/rollback and entity-rule tab shell.
 */

"use client";

import { useState } from "react";
import { Button } from "../ui/button";
import { Spinner } from "../ui/spinner";
import { StatusBanner } from "../ui/status-banner";
import { STALE_ROW_VERSION_COPY } from "../../lib/admin-copy";
import { EntityRulesPanel } from "./entity-rules-panel";
import { GlossaryPanel } from "./glossary-panel";
import { useCurationMutations } from "./hooks/use-curation-mutations";
import shellStyles from "./admin-shell.module.css";
import tableStyles from "./admin-tables.module.css";

const styles = { ...shellStyles, ...tableStyles };

/**
 * Curation tab with Glossary and Entity rules.
 *
 * @returns Nested tabs. Approve still posts `{ row_version }` only.
 */
export function CurationPanel() {
  const curation = useCurationMutations();
  const [inner, setInner] = useState<"glossary" | "rules">("glossary");

  if (!curation.meFetched) {
    return <Spinner label="Loading curation" />;
  }

  if (!curation.canMutate) {
    return (
      <p className={styles.muted}>
        Curation is limited to owners and admins.
      </p>
    );
  }

  return (
    <div className={styles.stack}>
      {curation.error ? (
        <StatusBanner kind="error" role="alert">
          {curation.error}
        </StatusBanner>
      ) : null}
      {curation.staleConflict ? (
        <StatusBanner kind="warning" role="alert">
          {STALE_ROW_VERSION_COPY}{" "}
          <Button
            type="button"
            data-action-id="admin.entity_rule.reload"
            onClick={curation.reloadRules}
          >
            Reload rule
          </Button>
        </StatusBanner>
      ) : null}
      {curation.outcome ? (
        <StatusBanner kind="success" role="status">
          {curation.outcome}
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
        <GlossaryPanel curation={curation} />
      ) : (
        <EntityRulesPanel curation={curation} />
      )}
    </div>
  );
}
