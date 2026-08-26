/**
 * Guided plan column list. Does not fetch or compile.
 */

"use client";

import type { TablePlanDraft } from "../../../lib/table-plan";
import { Button } from "../../ui/button";
import { Icon } from "../../ui/icon";
import { Input } from "../../ui/input";
import styles from "../tables.module.css";

export type ColumnsSectionProps = {
  columns: readonly string[];
  patchDraft: (patch: Partial<TablePlanDraft>) => void;
};

/**
 * Render add/remove column inputs.
 *
 * @param props - Column ids and draft patcher.
 * @returns Columns section.
 */
export function ColumnsSection({ columns, patchDraft }: ColumnsSectionProps) {
  return (
    <div className={styles.section}>
      <h3>Columns</h3>
      {columns.map((column, index) => (
        <div key={`column-${index}`} className={styles.repeatRow}>
          <Input
            id={`plan-column-${index}`}
            label="Column"
            value={column}
            onChange={(event) => {
              const next = [...columns];
              next[index] = event.target.value;
              patchDraft({ columns: next });
            }}
          />
          <Button
            type="button"
            size="icon"
            aria-label={`Remove column ${index + 1}`}
            onClick={() =>
              patchDraft({
                columns: columns.filter((_, itemIndex) => itemIndex !== index),
              })
            }
          >
            <Icon name="close" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="secondary"
        size="compact"
        onClick={() => patchDraft({ columns: [...columns, ""] })}
      >
        Add column
      </Button>
    </div>
  );
}
