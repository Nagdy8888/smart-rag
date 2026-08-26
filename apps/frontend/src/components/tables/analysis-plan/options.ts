/**
 * Allow-listed select options for the guided table plan.
 */

import {
  TABLE_AGGREGATION_OPS,
  TABLE_PREDICATE_OPERATORS,
  TABLE_SORT_DIRECTIONS,
} from "../../../lib/table-plan";

/** Predicate operator labels. */
export const OPERATOR_OPTIONS = TABLE_PREDICATE_OPERATORS.map((item) => ({
  value: item,
  label: item,
}));

/** Aggregation operator labels. */
export const AGGREGATION_OPTIONS = TABLE_AGGREGATION_OPS.map((item) => ({
  value: item,
  label: item,
}));

/** Sort direction labels. */
export const SORT_OPTIONS = TABLE_SORT_DIRECTIONS.map((item) => ({
  value: item,
  label: item,
}));
