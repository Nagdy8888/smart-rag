/**
 * Labeled text input. Error state is visual; it is not a server 400.
 */

"use client";

import { useState, type InputHTMLAttributes, type ReactNode } from "react";
import { Icon, type IconName } from "./icon";
import styles from "./styles/controls.module.css";

export type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  /** Visible English label. */
  label: ReactNode;
  /** Optional control beside the label, such as a forgot-password link. */
  labelEnd?: ReactNode;
  /** Optional leading glyph inside the field. */
  leadingIcon?: IconName;
  /** Optional error text announced with `aria-describedby`. */
  error?: string;
  /** Show a password visibility toggle when `type` is password. */
  revealable?: boolean;
  /** Drop the 520px field cap so the control can fill its parent. */
  fullWidth?: boolean;
};

/**
 * Render a labeled input with optional error styling and password reveal.
 *
 * @param props - Native input attributes plus `label`, `labelEnd`,
 *   `leadingIcon`, `error`, `revealable`, and `fullWidth`.
 * @returns Field with associated label. No fetch side effects.
 */
export function Input({
  label,
  labelEnd,
  leadingIcon,
  error,
  id,
  className,
  type = "text",
  revealable = false,
  fullWidth = false,
  ...rest
}: InputProps) {
  const [revealed, setRevealed] = useState(false);
  const inputId =
    id ?? (typeof label === "string" ? label.replace(/\s+/g, "-").toLowerCase() : undefined);
  const errorId = error && inputId ? `${inputId}-error` : undefined;
  const isPassword = type === "password";
  const showReveal = revealable && isPassword;
  const resolvedType = showReveal && revealed ? "text" : type;
  const combined = [
    styles.control,
    leadingIcon ? styles.controlWithLeading : undefined,
    showReveal ? styles.controlWithAddon : undefined,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={[styles.field, fullWidth ? styles.fieldFull : undefined].filter(Boolean).join(" ")}>
      <span className={styles.labelRow}>
        <label htmlFor={inputId}>{label}</label>
        {labelEnd}
      </span>
      <span className={styles.controlWrap}>
        {leadingIcon ? (
          <span className={styles.leadingGlyph} aria-hidden="true">
            <Icon name={leadingIcon} />
          </span>
        ) : null}
        <input
          id={inputId}
          className={combined}
          aria-invalid={error ? true : undefined}
          aria-describedby={errorId}
          {...rest}
          type={resolvedType}
        />
        {showReveal ? (
          <button
            type="button"
            className={styles.addonButton}
            onClick={() => setRevealed((value) => !value)}
            aria-label={revealed ? "Hide password" : "Show password"}
          >
            <Icon name={revealed ? "eyeOff" : "eye"} />
          </button>
        ) : null}
      </span>
      {error ? (
        <span id={errorId} role="status">
          {error}
        </span>
      ) : null}
    </div>
  );
}
