/**
 * Guided plan comparison editor. Does not fetch or compile.
 */

"use client";

import type {
  TableAggregationDraft,
  TablePlanDraft,
} from "../../../lib/table-plan";
import { Button } from "../../ui/button";
import { Icon } from "../../ui/icon";
import { Input } from "../../ui/input";
import { Select } from "../../ui/select";
import styles from "../tables.module.css";
import { AGGREGATION_OPTIONS } from "./options";
import { PredicateRow } from "./predicate-row";

export type ComparisonSectionProps = {
  draft: TablePlanDraft;
  patchDraft: (patch: Partial<TablePlanDraft>) => void;
};

/**
 * Render optional two-sided comparison filters.
 *
 * @param props - Full draft and patcher.
 * @returns Comparison section.
 */
export function ComparisonSection({ draft, patchDraft }: ComparisonSectionProps) {
  return (
    <div className={styles.section}>
      <h3>Comparison</h3>
      {draft.comparison ? (
        <div className={styles.comparison}>
          <div className={styles.repeatRow}>
            <Select
              id="comparison-op"
              label="Comparison aggregation"
              value={draft.comparison.aggregation}
              options={AGGREGATION_OPTIONS}
              onChange={(event) => {
                if (draft.comparison === null) {
                  return;
                }
                patchDraft({
                  comparison: {
                    ...draft.comparison,
                    aggregation: event.target.value as TableAggregationDraft["op"],
                  },
                });
              }}
            />
            <Input
              id="comparison-column"
              label="Comparison column"
              value={draft.comparison.column}
              onChange={(event) => {
                if (draft.comparison === null) {
                  return;
                }
                patchDraft({
                  comparison: {
                    ...draft.comparison,
                    column: event.target.value,
                  },
                });
              }}
            />
            <Button
              type="button"
              size="icon"
              aria-label="Remove comparison"
              onClick={() => patchDraft({ comparison: null })}
            >
              <Icon name="close" />
            </Button>
          </div>
          <p className={styles.muted}>Left filters</p>
          {draft.comparison.left.map((filter, index) => (
            <PredicateRow
              key={`left-${index}`}
              idPrefix={`left-${index}`}
              row={filter}
              removeLabel={`Remove left filter ${index + 1}`}
              onChange={(row) => {
                if (draft.comparison === null) {
                  return;
                }
                const left = [...draft.comparison.left];
                left[index] = row;
                patchDraft({ comparison: { ...draft.comparison, left } });
              }}
              onRemove={() => {
                if (draft.comparison === null) {
                  return;
                }
                patchDraft({
                  comparison: {
                    ...draft.comparison,
                    left: draft.comparison.left.filter(
                      (_, itemIndex) => itemIndex !== index,
                    ),
                  },
                });
              }}
            />
          ))}
          <Button
            type="button"
            onClick={() => {
              if (draft.comparison === null) {
                return;
              }
              patchDraft({
                comparison: {
                  ...draft.comparison,
                  left: [
                    ...draft.comparison.left,
                    { column: "", operator: "eq", value: "" },
                  ],
                },
              });
            }}
          >
            Add left filter
          </Button>
          <p className={styles.muted}>Right filters</p>
          {draft.comparison.right.map((filter, index) => (
            <PredicateRow
              key={`right-${index}`}
              idPrefix={`right-${index}`}
              row={filter}
              removeLabel={`Remove right filter ${index + 1}`}
              onChange={(row) => {
                if (draft.comparison === null) {
                  return;
                }
                const right = [...draft.comparison.right];
                right[index] = row;
                patchDraft({ comparison: { ...draft.comparison, right } });
              }}
              onRemove={() => {
                if (draft.comparison === null) {
                  return;
                }
                patchDraft({
                  comparison: {
                    ...draft.comparison,
                    right: draft.comparison.right.filter(
                      (_, itemIndex) => itemIndex !== index,
                    ),
                  },
                });
              }}
            />
          ))}
          <Button
            type="button"
            onClick={() => {
              if (draft.comparison === null) {
                return;
              }
              patchDraft({
                comparison: {
                  ...draft.comparison,
                  right: [
                    ...draft.comparison.right,
                    { column: "", operator: "eq", value: "" },
                  ],
                },
              });
            }}
          >
            Add right filter
          </Button>
        </div>
      ) : (
        <Button
          type="button"
          onClick={() =>
            patchDraft({
              comparison: {
                aggregation: "sum",
                column: "",
                left: [],
                right: [],
              },
            })
          }
        >
          Add comparison
        </Button>
      )}
    </div>
  );
}
