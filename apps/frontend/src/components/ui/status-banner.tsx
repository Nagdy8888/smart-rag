/**
 * Page-level status banner. `role="status"` by default; errors use `alert`.
 */

"use client";

import type { ReactNode } from "react";
import { useEffect, useRef } from "react";
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
  /**
   * Move keyboard focus onto this banner when it appears. Defaults to true
   * for `role="alert"` (426/402/MFA/error).
   */
  autoFocus?: boolean;
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
 * Blocking alerts receive `tabIndex={-1}` and `focus()` on mount. No HTML.
 */
export function StatusBanner({
  children,
  kind = "info",
  role = "status",
  autoFocus,
}: StatusBannerProps) {
  const ref = useRef<HTMLParagraphElement>(null);
  const shouldFocus = autoFocus ?? role === "alert";
  const kindClass = KIND_CLASS[kind];
  const combined = [styles.banner, kindClass].filter(Boolean).join(" ");
  const body = typeof children === "string" ? displayText(children) : children;

  useEffect(() => {
    if (shouldFocus) {
      ref.current?.focus();
    }
  }, [shouldFocus, body]);

  return (
    <p
      ref={ref}
      className={combined}
      role={role}
      data-kind={kind}
      tabIndex={shouldFocus ? -1 : undefined}
    >
      {kind === "warning" ? (
        <span className={styles.warningGlyph} aria-hidden="true">
          !
        </span>
      ) : null}
      {body}
    </p>
  );
}
