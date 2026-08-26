"use client";

/**
 * Accessible button primitive. Typed handlers only; no inline scripts.
 */

import {
  forwardRef,
  useId,
  type ButtonHTMLAttributes,
  type MouseEvent,
  type ReactNode,
} from "react";
import styles from "./ui.module.css";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "danger"
  | "ghost"
  | "dangerQuiet";

export type ButtonSize = "md" | "compact" | "lg" | "icon";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** Visual variant. Default `secondary`. */
  variant?: ButtonVariant;
  /** `icon` is a 36px square. `compact` is 32px. `lg` is 44px. Default 40px. */
  size?: ButtonSize;
  /** Accessible name comes from children or `aria-label`. */
  children: ReactNode;
  /** Blocks duplicate submit and shows a present-participle label. */
  pending?: boolean;
  /** Label while pending, such as `Sending…`. */
  pendingLabel?: string;
  /** Visible reason when disabled. Required for disabled actions. */
  disabledReason?: string;
};

const VARIANT_CLASS: Record<ButtonVariant, string | undefined> = {
  primary: styles.buttonPrimary,
  secondary: undefined,
  danger: styles.buttonDanger,
  ghost: styles.buttonGhost,
  dangerQuiet: styles.buttonDangerQuiet,
};

const SIZE_CLASS: Record<ButtonSize, string | undefined> = {
  md: undefined,
  compact: styles.buttonCompact,
  lg: styles.buttonLarge,
  icon: styles.iconButton,
};

/**
 * Render a keyboard-operable control with the 2px focus ring from globals.
 *
 * @param props - Native button attributes plus visual/pending contract.
 * @returns Button element. Pending disables the control without swallowing errors.
 * @throws Never. Disabled state is visual only and not authorization.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    className,
    type = "button",
    children,
    pending = false,
    pendingLabel,
    disabledReason,
    disabled,
    onClick,
    ...rest
  },
  ref,
) {
  const blocked = Boolean(disabled || pending);
  const hintId = useId();
  const combined = [
    styles.button,
    VARIANT_CLASS[variant],
    SIZE_CLASS[size],
    pending ? styles.buttonPending : undefined,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  /**
   * Ignore clicks while pending or disabled so duplicate submits cannot start.
   *
   * @param event - Native click.
   */
  function handleClick(event: MouseEvent<HTMLButtonElement>): void {
    if (blocked) {
      event.preventDefault();
      return;
    }
    onClick?.(event);
  }

  const label = pending ? (pendingLabel ?? children) : children;
  const hint =
    blocked && disabledReason ? (
      <span id={hintId} className={styles.fieldHint}>
        {disabledReason}
      </span>
    ) : null;
  const control = (
    <button
      ref={ref}
      type={type}
      className={combined}
      disabled={blocked}
      aria-busy={pending || undefined}
      aria-describedby={blocked && disabledReason ? hintId : undefined}
      onClick={handleClick}
      {...rest}
    >
      {pending ? <span className={styles.buttonSpinner} aria-hidden="true" /> : null}
      {label}
    </button>
  );
  if (hint === null) {
    return control;
  }
  return (
    <span className={styles.buttonWrap}>
      {control}
      {hint}
    </span>
  );
});

/**
 * Primary call-to-action. Same contract as `Button` with `variant="primary"`.
 *
 * @param props - Button props.
 * @returns Primary button.
 */
export function PrimaryAction(props: ButtonProps) {
  return <Button {...props} variant="primary" />;
}

/**
 * Async submit wrapper. Owning form still renders success/error copy.
 *
 * @param props - Button props including pending labels.
 * @returns Button that blocks duplicate submits while pending.
 */
export function AsyncButton(props: ButtonProps) {
  return <Button {...props} />;
}
