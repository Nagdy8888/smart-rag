/**
 * Labeled textarea for composer and comments. Native caret/IME only.
 */

import type { ReactNode, TextareaHTMLAttributes } from "react";
import styles from "./styles/controls.module.css";

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  /** Visible English label. */
  label: ReactNode;
  /** Optional error text. */
  error?: string;
  /** Drop the 520px field cap so the control can fill its parent. */
  fullWidth?: boolean;
};

/**
 * Render a labeled multiline control.
 *
 * @param props - Native textarea attributes plus `label` and optional
 *   `fullWidth` to fill the parent instead of the 520px field cap.
 * @returns Label wrapping the control. No custom bidi editor.
 */
export function Textarea({
  label,
  error,
  id,
  className,
  fullWidth = false,
  ...rest
}: TextareaProps) {
  const inputId =
    id ?? (typeof label === "string" ? label.replace(/\s+/g, "-").toLowerCase() : undefined);
  const errorId = error && inputId ? `${inputId}-error` : undefined;
  const combined = [styles.control, styles.textarea, className]
    .filter(Boolean)
    .join(" ");
  const fieldClass = [styles.field, fullWidth ? styles.fieldFull : undefined]
    .filter(Boolean)
    .join(" ");
  return (
    <label className={fieldClass} htmlFor={inputId}>
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
