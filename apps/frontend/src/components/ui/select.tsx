/**
 * Native labeled select. Never a custom listbox.
 */

import type { SelectHTMLAttributes } from "react";
import styles from "./styles/controls.module.css";

export type SelectOption = {
  /** Option value submitted with the form. */
  value: string;
  /** Visible English label. */
  label: string;
  /** When true, the option cannot be chosen. */
  disabled?: boolean;
};

export type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> & {
  /** Visible English label. */
  label: string;
  /** Controlled value. */
  value: string;
  /** Typed options rendered as native `<option>` nodes. */
  options: readonly SelectOption[];
  /** Optional supporting text. */
  description?: string;
  /** Optional error text announced with `aria-describedby`. */
  error?: string;
};

/**
 * Render a labeled native `<select>`.
 *
 * @param props - Label, value, options, optional description/error, native attrs.
 * @returns Field with associated label. No fetch side effects.
 */
export function Select({
  label,
  value,
  options,
  description,
  error,
  id,
  className,
  ...rest
}: SelectProps) {
  const selectId = id ?? label.replace(/\s+/g, "-").toLowerCase();
  const descriptionId = description ? `${selectId}-description` : undefined;
  const errorId = error ? `${selectId}-error` : undefined;
  const describedBy = [descriptionId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={styles.field}>
      <label htmlFor={selectId}>{label}</label>
      {description ? (
        <p id={descriptionId} className={styles.fieldHint}>
          {description}
        </p>
      ) : null}
      <select
        id={selectId}
        className={[styles.control, className].filter(Boolean).join(" ")}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...rest}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
      {error ? (
        <p id={errorId} role="status">
          {error}
        </p>
      ) : null}
    </div>
  );
}
