/**
 * Guided plan filter list. Does not fetch or compile.
 */

"use client";

import type { TablePlanDraft, TablePredicateDraft } from "../../../lib/table-plan";
import { Button } from "../../ui/button";
import styles from "../tables.module.css";
import { PredicateRow } from "./predicate-row";

export type FiltersSectionProps = {
  filters: readonly TablePredicateDraft[];
  patchDraft: (patch: Partial<TablePlanDraft>) => void;
};

/**
 * Render add/remove filter rows.
 *
 * @param props - Filters and draft patcher.
 * @returns Filters section.
 */
export function FiltersSection({ filters, patchDraft }: FiltersSectionProps) {
  return (
    <div className={styles.section}>
      <h3>Filters</h3>
      {filters.map((filter, index) => (
        <PredicateRow
          key={`filter-${index}`}
          idPrefix={`filter-${index}`}
          row={filter}
          removeLabel={`Remove filter ${index + 1}`}
          onChange={(row) => {
            const next = [...filters];
            next[index] = row;
            patchDraft({ filters: next });
          }}
          onRemove={() =>
            patchDraft({
              filters: filters.filter((_, itemIndex) => itemIndex !== index),
            })
          }
        />
      ))}
      <Button
        type="button"
        variant="secondary"
        size="compact"
        onClick={() =>
          patchDraft({
            filters: [...filters, { column: "", operator: "eq", value: "" }],
          })
        }
      >
        Add filter
      </Button>
    </div>
  );
}
