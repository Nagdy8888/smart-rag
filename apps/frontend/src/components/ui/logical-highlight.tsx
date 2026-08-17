/**
 * Logical-offset highlight rendered as React text nodes.
 */

import { highlightLogicalRange } from "../../lib/highlight-logical-range";
import { displayText } from "../../lib/safe-text";
import styles from "./ui.module.css";

export type LogicalHighlightProps = {
  /** Canonical logical text. Never HTML. */
  text: unknown;
  /** Inclusive Unicode codepoint offset. */
  start: number;
  /** Exclusive Unicode codepoint offset. */
  end: number;
};

/**
 * Highlight `[start, end)` by codepoint and render text children only.
 *
 * @param props - Canonical text plus logical offsets.
 * @returns Isolated `dir="auto"` span. Match is a `<mark>` of text nodes.
 * @remarks
 * Security: no `innerHTML`. Offsets are not visual-order indexes.
 */
export function LogicalHighlight({ text, start, end }: LogicalHighlightProps) {
  const parts = highlightLogicalRange(displayText(text), start, end);
  return (
    <span dir="auto" className={styles.userText}>
      {parts.before}
      {parts.match !== "" ? (
        <mark className={styles.logicalMark}>{parts.match}</mark>
      ) : null}
      {parts.after}
    </span>
  );
}
