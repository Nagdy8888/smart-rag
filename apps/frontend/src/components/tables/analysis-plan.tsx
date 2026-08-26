/**
 * Guided TableQueryPlan builder. No SQL editor, Export, Save, or Share.
 */

"use client";

import { Button, PrimaryAction } from "../ui/button";
import { Icon } from "../ui/icon";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import { UserText } from "../ui/user-text";
import {
  TABLE_AGGREGATION_OPS,
  TABLE_PREDICATE_OPERATORS,
  TABLE_SORT_DIRECTIONS,
  type TableAggregationDraft,
  type TablePlanDraft,
  type TablePredicateDraft,
  type TableSortDraft,
} from "../../lib/table-plan";
import type { TableManifestResponse } from "../../lib/types";
import styles from "./tables.module.css";

export type AnalysisPlanProps = {
  /** Authorized manifests. */
  manifests: readonly TableManifestResponse[];
  /** Currently selected accessible table. */
  selected: TableManifestResponse | null;
  /** Guided draft. Preserved across analyze failures. */
  draft: TablePlanDraft;
  /** Analyze in flight. */
  pending: boolean;
  /** Sidebar/select change. */
  onSelectTableId: (tableId: string) => void;
  /** Replace the draft. */
  onDraftChange: (draft: TablePlanDraft) => void;
  /** Compile and POST. */
  onAnalyze: () => void;
};

const OPERATOR_OPTIONS = TABLE_PREDICATE_OPERATORS.map((item) => ({
  value: item,
  label: item,
}));

const AGGREGATION_OPTIONS = TABLE_AGGREGATION_OPS.map((item) => ({
  value: item,
  label: item,
}));

const SORT_OPTIONS = TABLE_SORT_DIRECTIONS.map((item) => ({
  value: item,
  label: item,
}));

/**
 * Render the Analysis plan card.
 *
 * @param props - Manifests, draft, and Analyze handler.
 * @returns Plan form. Does not fetch.
 */
export function AnalysisPlan({
  manifests,
  selected,
  draft,
  pending,
  onSelectTableId,
  onDraftChange,
  onAnalyze,
}: AnalysisPlanProps) {
  const tableOptions = [
    { value: "", label: "Select a table", disabled: true },
    ...manifests.map((item) => ({
      value: item.table_id,
      label: item.sheet_name
        ? `${item.table_name} (${item.sheet_name})`
        : item.table_name,
    })),
  ];

  /**
   * Patch the draft immutably.
   *
   * @param patch - Partial draft.
   */
  function patchDraft(patch: Partial<TablePlanDraft>): void {
    onDraftChange({ ...draft, ...patch });
  }

  return (
    <section className={styles.card} aria-label="Analysis plan">
      <h2>Analysis plan</h2>
      <Select
        label="Table"
        value={selected?.table_id ?? ""}
        options={tableOptions}
        onChange={(event) => onSelectTableId(event.target.value)}
      />
      {selected ? (
        <p className={styles.muted}>
          Document{" "}
          <span className={styles.mono}>
            <UserText value={selected.document_id} />
          </span>
        </p>
      ) : null}

      <div className={styles.section}>
        <h3>Columns</h3>
        {draft.columns.map((column, index) => (
          <div key={`column-${index}`} className={styles.repeatRow}>
            <Input
              id={`plan-column-${index}`}
              label="Column"
              value={column}
              onChange={(event) => {
                const columns = [...draft.columns];
                columns[index] = event.target.value;
                patchDraft({ columns });
              }}
            />
            <Button
              type="button"
              size="icon"
              aria-label={`Remove column ${index + 1}`}
              onClick={() =>
                patchDraft({
                  columns: draft.columns.filter((_, itemIndex) => itemIndex !== index),
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
          onClick={() => patchDraft({ columns: [...draft.columns, ""] })}
        >
          Add column
        </Button>
      </div>

      <div className={styles.section}>
        <h3>Filters</h3>
        {draft.filters.map((filter, index) => (
          <PredicateRow
            key={`filter-${index}`}
            idPrefix={`filter-${index}`}
            row={filter}
            removeLabel={`Remove filter ${index + 1}`}
            onChange={(row) => {
              const filters = [...draft.filters];
              filters[index] = row;
              patchDraft({ filters });
            }}
            onRemove={() =>
              patchDraft({
                filters: draft.filters.filter((_, itemIndex) => itemIndex !== index),
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
              filters: [
                ...draft.filters,
                { column: "", operator: "eq", value: "" },
              ],
            })
          }
        >
          Add filter
        </Button>
      </div>

      <div className={styles.section}>
        <h3>Aggregation</h3>
        {draft.aggregations.map((item, index) => (
          <div key={`agg-${index}`} className={styles.repeatRow}>
            <Select
              id={`agg-op-${index}`}
              label="Aggregation"
              value={item.op}
              options={AGGREGATION_OPTIONS}
              onChange={(event) => {
                const aggregations = [...draft.aggregations];
                const current = aggregations[index];
                if (current === undefined) {
                  return;
                }
                aggregations[index] = {
                  ...current,
                  op: event.target.value as TableAggregationDraft["op"],
                };
                patchDraft({ aggregations });
              }}
            />
            <Input
              id={`agg-column-${index}`}
              label="Aggregation column"
              value={item.column}
              onChange={(event) => {
                const aggregations = [...draft.aggregations];
                const current = aggregations[index];
                if (current === undefined) {
                  return;
                }
                aggregations[index] = { ...current, column: event.target.value };
                patchDraft({ aggregations });
              }}
            />
            <Button
              type="button"
              size="icon"
              aria-label={`Remove aggregation ${index + 1}`}
              onClick={() =>
                patchDraft({
                  aggregations: draft.aggregations.filter(
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
                ...draft.aggregations,
                { op: "count", column: "", alias: "" },
              ],
            })
          }
        >
          Add aggregation
        </Button>
      </div>

      <div className={styles.section}>
        <h3>Group by</h3>
        {draft.groupBy.map((column, index) => (
          <div key={`group-${index}`} className={styles.repeatRow}>
            <Input
              id={`group-column-${index}`}
              label="Group by column"
              value={column}
              onChange={(event) => {
                const groupBy = [...draft.groupBy];
                groupBy[index] = event.target.value;
                patchDraft({ groupBy });
              }}
            />
            <Button
              type="button"
              size="icon"
              aria-label={`Remove group by ${index + 1}`}
              onClick={() =>
                patchDraft({
                  groupBy: draft.groupBy.filter((_, itemIndex) => itemIndex !== index),
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
          onClick={() => patchDraft({ groupBy: [...draft.groupBy, ""] })}
        >
          Add group by
        </Button>
      </div>

      <div className={styles.section}>
        <h3>Sort</h3>
        {draft.sorts.map((item, index) => (
          <div key={`sort-${index}`} className={styles.repeatRow}>
            <Input
              id={`sort-column-${index}`}
              label="Sort column"
              value={item.column}
              onChange={(event) => {
                const sorts = [...draft.sorts];
                const current = sorts[index];
                if (current === undefined) {
                  return;
                }
                sorts[index] = { ...current, column: event.target.value };
                patchDraft({ sorts });
              }}
            />
            <Select
              id={`sort-dir-${index}`}
              label="Sort direction"
              value={item.direction}
              options={SORT_OPTIONS}
              onChange={(event) => {
                const sorts = [...draft.sorts];
                const current = sorts[index];
                if (current === undefined) {
                  return;
                }
                sorts[index] = {
                  ...current,
                  direction: event.target.value as TableSortDraft["direction"],
                };
                patchDraft({ sorts });
              }}
            />
            <Button
              type="button"
              size="icon"
              aria-label={`Remove sort ${index + 1}`}
              onClick={() =>
                patchDraft({
                  sorts: draft.sorts.filter((_, itemIndex) => itemIndex !== index),
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
              sorts: [...draft.sorts, { column: "", direction: "asc" }],
            })
          }
        >
          Add sort
        </Button>
      </div>

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
                      aggregation: event.target
                        .value as TableAggregationDraft["op"],
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

      <div className={styles.planActions}>
        <PrimaryAction
          type="button"
          data-action-id="tables.analyze"
          pending={pending}
          pendingLabel="Analyzing…"
          disabled={selected === null}
          disabledReason={
            selected === null ? "Select an available table." : undefined
          }
          onClick={onAnalyze}
        >
          Analyze
        </PrimaryAction>
      </div>
    </section>
  );
}

/**
 * One predicate editor row.
 *
 * @param props - Row, ids, and handlers.
 * @returns Filter controls.
 */
function PredicateRow({
  idPrefix,
  row,
  removeLabel,
  onChange,
  onRemove,
}: {
  idPrefix: string;
  row: TablePredicateDraft;
  removeLabel: string;
  onChange: (row: TablePredicateDraft) => void;
  onRemove: () => void;
}) {
  return (
    <div className={styles.repeatRow}>
      <Input
        id={`${idPrefix}-column`}
        label="Filter column"
        value={row.column}
        onChange={(event) => onChange({ ...row, column: event.target.value })}
      />
      <Select
        id={`${idPrefix}-operator`}
        label="Operator"
        value={row.operator}
        options={OPERATOR_OPTIONS}
        onChange={(event) =>
          onChange({
            ...row,
            operator: event.target.value as TablePredicateDraft["operator"],
          })
        }
      />
      <Input
        id={`${idPrefix}-value`}
        label="Filter value"
        value={row.value}
        onChange={(event) => onChange({ ...row, value: event.target.value })}
      />
      <Button type="button" size="icon" aria-label={removeLabel} onClick={onRemove}>
        <Icon name="close" />
      </Button>
    </div>
  );
}
