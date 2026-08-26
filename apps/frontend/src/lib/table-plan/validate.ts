/**
 * Column, SQL/path, and predicate-value guards for table plans.
 */

import type { TablePredicate, TablePredicateOperator } from "../types";
import { TABLE_ROW_LIMIT_DEFAULT, TABLE_ROW_LIMIT_MAX } from "./draft";

const COLUMN_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

const SQL_OR_PATH_TOKENS = [
  "select ",
  " attach",
  "../",
  "://",
  "pragma",
  "copy ",
  ";",
] as const;

/**
 * Clamp analyze row_limit to 1–1000.
 *
 * @param value - Raw input.
 * @returns Integer in range, default 100.
 */
export function clampTableRowLimit(value: number): number {
  if (!Number.isFinite(value)) {
    return TABLE_ROW_LIMIT_DEFAULT;
  }
  return Math.min(TABLE_ROW_LIMIT_MAX, Math.max(1, Math.floor(value)));
}

/**
 * Return whether a column id is a safe internal identifier.
 *
 * @param value - Candidate id.
 * @returns True when it matches the plan regex.
 */
export function isInternalColumnId(value: string): boolean {
  return COLUMN_RE.test(value) && value.length <= 64;
}

/**
 * Return whether a string looks like SQL, a path, or a URL.
 *
 * @param value - Untrusted scalar.
 * @returns True when the value must not be posted.
 */
export function looksLikeSqlOrPath(value: string): boolean {
  const lowered = value.toLowerCase();
  return SQL_OR_PATH_TOKENS.some((token) => lowered.includes(token));
}

/**
 * Parse a predicate value. `in` uses a comma-separated list.
 *
 * @param raw - Form text.
 * @param operator - Allow-listed operator.
 * @returns Scalar or list suitable for `TablePredicate.value`.
 */
export function parsePredicateValue(
  raw: string,
  operator: TablePredicateOperator,
): TablePredicate["value"] {
  if (operator === "in") {
    return raw.split(",").map((part) => parsePredicateScalar(part.trim()));
  }
  return parsePredicateScalar(raw);
}

/**
 * Parse one predicate scalar.
 *
 * @param raw - Form text.
 * @returns JSON scalar.
 */
function parsePredicateScalar(raw: string): string | number | boolean | null {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return null;
  }
  if (trimmed === "true") {
    return true;
  }
  if (trimmed === "false") {
    return false;
  }
  if (/^-?\d+(?:\.\d+)?$/.test(trimmed)) {
    return Number(trimmed);
  }
  return trimmed;
}
