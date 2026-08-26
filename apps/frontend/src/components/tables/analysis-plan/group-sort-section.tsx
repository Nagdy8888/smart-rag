/**
 * Guided plan group-by and sort lists. Does not fetch or compile.
 */

"use client";

import type { TablePlanDraft, TableSortDraft } from "../../../lib/table-plan";
import { Button } from "../../ui/button";
import { Icon } from "../../ui/icon";
import { Input } from "../../ui/input";
import { Select } from "../../ui/select";
import styles from "../tables.module.css";
import { SORT_OPTIONS } from "./options";

export type GroupSortSectionProps = {
  groupBy: readonly string[];
  sorts: readonly TableSortDraft[];
  patchDraft: (patch: Partial<TablePlanDraft>) => void;
};

/**
 * Render group-by and sort editors.
 *
 * @param props - Group/sort drafts and patcher.
 * @returns Two stacked sections.
 */
export function GroupSortSection({
  groupBy,
  sorts,
  patchDraft,
}: GroupSortSectionProps) {
  return (
    <>
      <div className={styles.section}>
        <h3>Group by</h3>
        {groupBy.map((column, index) => (
          <div key={`group-${index}`} className={styles.repeatRow}>
            <Input
              id={`group-column-${index}`}
              label="Group by column"
              value={column}
              onChange={(event) => {
                const next = [...groupBy];
                next[index] = event.target.value;
                patchDraft({ groupBy: next });
              }}
            />
            <Button
              type="button"
              size="icon"
              aria-label={`Remove group by ${index + 1}`}
              onClick={() =>
                patchDraft({
                  groupBy: groupBy.filter((_, itemIndex) => itemIndex !== index),
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
          onClick={() => patchDraft({ groupBy: [...groupBy, ""] })}
        >
          Add group by
        </Button>
      </div>
      <div className={styles.section}>
        <h3>Sort</h3>
        {sorts.map((item, index) => (
          <div key={`sort-${index}`} className={styles.repeatRow}>
            <Input
              id={`sort-column-${index}`}
              label="Sort column"
              value={item.column}
              onChange={(event) => {
                const next = [...sorts];
                const current = next[index];
                if (current === undefined) {
                  return;
                }
                next[index] = { ...current, column: event.target.value };
                patchDraft({ sorts: next });
              }}
            />
            <Select
              id={`sort-dir-${index}`}
              label="Sort direction"
              value={item.direction}
              options={SORT_OPTIONS}
              onChange={(event) => {
                const next = [...sorts];
                const current = next[index];
                if (current === undefined) {
                  return;
                }
                next[index] = {
                  ...current,
                  direction: event.target.value as TableSortDraft["direction"],
                };
                patchDraft({ sorts: next });
              }}
            />
            <Button
              type="button"
              size="icon"
              aria-label={`Remove sort ${index + 1}`}
              onClick={() =>
                patchDraft({
                  sorts: sorts.filter((_, itemIndex) => itemIndex !== index),
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
          onClick={() =>
            patchDraft({
              sorts: [...sorts, { column: "", direction: "asc" }],
            })
          }
        >
          Add sort
        </Button>
      </div>
    </>
  );
}
