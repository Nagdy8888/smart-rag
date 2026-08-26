/**
 * One predicate editor row. Does not fetch or compile.
 */

"use client";

import type { TablePredicateDraft } from "../../../lib/table-plan";
import { Button } from "../../ui/button";
import { Icon } from "../../ui/icon";
import { Input } from "../../ui/input";
import { Select } from "../../ui/select";
import styles from "../tables.module.css";
import { OPERATOR_OPTIONS } from "./options";

export type PredicateRowProps = {
  idPrefix: string;
  row: TablePredicateDraft;
  removeLabel: string;
  onChange: (row: TablePredicateDraft) => void;
  onRemove: () => void;
};

/**
 * Render column, operator, value, and remove controls.
 *
 * @param props - Row, ids, and handlers.
 * @returns Filter controls.
 */
export function PredicateRow({
  idPrefix,
  row,
  removeLabel,
  onChange,
  onRemove,
}: PredicateRowProps) {
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
