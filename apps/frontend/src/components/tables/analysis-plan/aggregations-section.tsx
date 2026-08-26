/**
 * Guided plan aggregation list. Does not fetch or compile.
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

export type AggregationsSectionProps = {
  aggregations: readonly TableAggregationDraft[];
  patchDraft: (patch: Partial<TablePlanDraft>) => void;
};

/**
 * Render add/remove aggregation rows.
 *
 * @param props - Aggregations and draft patcher.
 * @returns Aggregation section.
 */
export function AggregationsSection({
  aggregations,
  patchDraft,
}: AggregationsSectionProps) {
  return (
    <div className={styles.section}>
      <h3>Aggregation</h3>
      {aggregations.map((item, index) => (
        <div key={`agg-${index}`} className={styles.repeatRow}>
          <Select
            id={`agg-op-${index}`}
            label="Aggregation"
            value={item.op}
            options={AGGREGATION_OPTIONS}
            onChange={(event) => {
              const next = [...aggregations];
              const current = next[index];
              if (current === undefined) {
                return;
              }
              next[index] = {
                ...current,
                op: event.target.value as TableAggregationDraft["op"],
              };
              patchDraft({ aggregations: next });
            }}
          />
          <Input
            id={`agg-column-${index}`}
            label="Aggregation column"
            value={item.column}
            onChange={(event) => {
              const next = [...aggregations];
              const current = next[index];
              if (current === undefined) {
                return;
              }
              next[index] = { ...current, column: event.target.value };
              patchDraft({ aggregations: next });
            }}
          />
          <Button
            type="button"
            size="icon"
            aria-label={`Remove aggregation ${index + 1}`}
            onClick={() =>
              patchDraft({
                aggregations: aggregations.filter(
                  (_, itemIndex) => itemIndex !== index,
                ),
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
            aggregations: [
              ...aggregations,
              { op: "count", column: "", alias: "" },
            ],
          })
        }
      >
        Add aggregation
      </Button>
    </div>
  );
}
