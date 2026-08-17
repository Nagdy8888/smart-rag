/**
 * Labeled textarea for composer and comments. Native caret/IME only.
 */

import type { ReactNode, TextareaHTMLAttributes } from "react";
import styles from "./ui.module.css";

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  /** Visible English label. */
  label: ReactNode;
  /** Optional error text. */
  error?: string;
};

/**
 * Render a labeled multiline control.
 *
 * @param props - Native textarea attributes plus `label`.
 * @returns Label wrapping the control. No custom bidi editor.
 */
export function Textarea({
  label,
  error,
  id,
  className,
  ...rest
}: TextareaProps) {
  const inputId =
    id ?? (typeof label === "string" ? label.replace(/\s+/g, "-").toLowerCase() : undefined);
  const errorId = error && inputId ? `${inputId}-error` : undefined;
  const combined = [styles.control, styles.textarea, className]
    .filter(Boolean)
    .join(" ");
  return (
    <label className={styles.field} htmlFor={inputId}>
      {label}
      <textarea
        id={inputId}
        className={combined}
        dir="auto"
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
