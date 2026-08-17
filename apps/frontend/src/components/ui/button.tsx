/**
 * Accessible button primitive. Typed handlers only; no inline scripts.
 */

import type { ButtonHTMLAttributes, ReactNode } from "react";
import styles from "./ui.module.css";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** Visual variant. Default `secondary`. */
  variant?: ButtonVariant;
  /** Accessible name comes from children or `aria-label`. */
  children: ReactNode;
};

const VARIANT_CLASS: Record<ButtonVariant, string | undefined> = {
  primary: styles.buttonPrimary,
  secondary: undefined,
  danger: styles.buttonDanger,
  ghost: styles.buttonGhost,
};

/**
 * Render a keyboard-operable control with the 2px focus ring from globals.
 *
 * @param props - Native button attributes plus `variant`.
 * @returns Button element. No network side effects.
 * @throws Never. Disabled state is visual only and not authorization.
 */
export function Button({
  variant = "secondary",
  className,
  type = "button",
  children,
  ...rest
}: ButtonProps) {
  const variantClass = VARIANT_CLASS[variant];
  const combined = [styles.button, variantClass, className]
    .filter(Boolean)
    .join(" ");
  return (
    <button type={type} className={combined} {...rest}>
      {children}
    </button>
  );
}
