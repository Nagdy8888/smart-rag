/**
 * Bidi-safe text nodes for untrusted user and model strings.
 */

import type { ReactNode } from "react";
import { displayText } from "../../lib/safe-text";
import styles from "./ui.module.css";

export type UserTextProps = {
  /** Untrusted value. Non-strings become empty. */
  value: unknown;
  /** Optional extra class names. */
  className?: string;
};

/**
 * Render hostile content as an isolated `dir="auto"` text node.
 *
 * @param props - Untrusted value. Never HTML.
 * @returns Span with `unicode-bidi: isolate`.
 * @remarks
 * Security: uses `displayText` and React text children. No HTML injection.
 * Side effects: none.
 */
export function UserText({ value, className }: UserTextProps): ReactNode {
  const combined = className ? `${styles.userText} ${className}` : styles.userText;
  return (
    <span dir="auto" className={combined}>
      {displayText(value)}
    </span>
  );
}

export type CodeTextProps = UserTextProps;

/**
 * Render codes, IDs, and URLs as LTR isolated text.
 *
 * @param props - Untrusted identifier or URL string.
 * @returns Span with `dir="ltr"`.
 * @remarks
 * Does not create an `href`. Callers must use `isSafeHttpUrl` first.
 */
export function CodeText({ value, className }: CodeTextProps): ReactNode {
  const combined = className ? `${styles.codeText} ${className}` : styles.codeText;
  return (
    <span dir="ltr" className={`${combined} code-isolate`}>
      {displayText(value)}
    </span>
  );
}
