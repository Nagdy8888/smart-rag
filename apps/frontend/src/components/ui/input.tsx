/**
 * Labeled text input. Error state is visual; it is not a server 400.
 */

import type { InputHTMLAttributes, ReactNode } from "react";
import styles from "./ui.module.css";

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  /** Visible English label. */
  label: ReactNode;
  /** Optional error text announced with `aria-describedby`. */
  error?: string;
};

/**
 * Render a labeled input with optional error styling.
 *
 * @param props - Native input attributes plus `label` and `error`.
 * @returns Label wrapping the control. No fetch side effects.
 */
export function Input({ label, error, id, className, ...rest }: InputProps) {
  const inputId = id ?? (typeof label === "string" ? label.replace(/\s+/g, "-").toLowerCase() : undefined);
  const errorId = error && inputId ? `${inputId}-error` : undefined;
  const combined = className ? `${styles.control} ${className}` : styles.control;
  return (
    <label className={styles.field} htmlFor={inputId}>
      {label}
      <input
        id={inputId}
        className={combined}
        aria-invalid={error ? true : undefined}
        aria-describedby={errorId}
        {...rest}
      />
      {error ? (
        <span id={errorId} role="status">
          {error}
        </span>
      ) : null}
    </label>
  );
}
