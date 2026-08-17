/**
 * Page-level status banner. `role="status"` by default; errors use `alert`.
 */

import type { ReactNode } from "react";
import { displayText } from "../../lib/safe-text";
import styles from "./ui.module.css";

export type StatusBannerKind = "info" | "warning" | "error" | "success";

export type StatusBannerProps = {
  /** Banner body. Strings are escaped via `displayText`. */
  children: ReactNode;
  /** Visual kind. Default `info`. */
  kind?: StatusBannerKind;
  /** Landmark role. Default `status`. Use `alert` for blocking failures. */
  role?: "status" | "alert";
};

const KIND_CLASS: Record<StatusBannerKind, string | undefined> = {
  info: undefined,
  warning: styles.bannerWarning,
  error: styles.bannerError,
  success: styles.bannerSuccess,
};

/**
 * Render a polite or assertive status region.
 *
 * @param props - Kind, role, and body.
 * @returns Element with `role="status"` or `role="alert"`.
 * @remarks
 * Moving focus onto the banner is a later packet concern. No HTML.
 */
export function StatusBanner({
  children,
  kind = "info",
  role = "status",
}: StatusBannerProps) {
  const kindClass = KIND_CLASS[kind];
  const combined = [styles.banner, kindClass].filter(Boolean).join(" ");
  const body = typeof children === "string" ? displayText(children) : children;
  return (
    <p className={combined} role={role} data-kind={kind}>
      {body}
    </p>
  );
}
