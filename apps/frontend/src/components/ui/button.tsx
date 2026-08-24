/**
 * Accessible button primitive. Typed handlers only; no inline scripts.
 */

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import styles from "./ui.module.css";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

export type ButtonSize = "md" | "icon";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** Visual variant. Default `secondary`. */
  variant?: ButtonVariant;
  /** `icon` is a 44px square for icon-only actions. */
  size?: ButtonSize;
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
 * @param props - Native button attributes plus `variant` and `size`.
 * @returns Button element. No network side effects.
 * @throws Never. Disabled state is visual only and not authorization.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    className,
    type = "button",
    children,
    ...rest
  },
  ref,
) {
  const variantClass = VARIANT_CLASS[variant];
  const combined = [
    styles.button,
    variantClass,
    size === "icon" ? styles.iconButton : undefined,
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button ref={ref} type={type} className={combined} {...rest}>
      {children}
    </button>
  );
});
