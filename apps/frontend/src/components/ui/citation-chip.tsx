/**
 * Citation index chip. List views must not show snippets.
 */

import { displayText } from "../../lib/safe-text";
import { UserText } from "./user-text";
import styles from "./styles/data-display.module.css";

export type CitationChipProps = {
  /** 1-based or server `citation_index`. */
  index: number;
  /** Optional citation id, rendered as isolated text when `label` is omitted. */
  citationId?: unknown;
  /** Human locator such as title and page. Preferred over `citationId`. */
  label?: unknown;
  /** Accessible name. Defaults to `Citation {index}`. */
  name?: string;
  /** When true, append signed unavailable copy supplied by the caller. */
  unavailable?: boolean;
  /** Optional safe http(s) href. Callers must pass `isSafeHttpUrl` first. */
  href?: string | null;
  /**
   * Select handler when the chip is a button. Receives the chip element
   * so a drawer can restore focus.
   */
  onSelect?: (trigger: HTMLButtonElement) => void;
};

/**
 * Render a citation chip with a locator label when one exists.
 *
 * @param props - Index, optional locator label/id/href, unavailable flag.
 * @returns Anchor when `href` is set, otherwise a button or span.
 * @remarks
 * Security: `href` is not validated here. Do not pass `javascript:` URLs.
 * Callers set `href` only for `source_kind=web` after `isSafeHttpUrl`.
 * Company chips stay buttons. Passage text is never rendered.
 */
export function CitationChip({
  index,
  citationId,
  label,
  name,
  unavailable = false,
  href = null,
  onSelect,
}: CitationChipProps) {
  const fallbackName = `Citation ${String(index)}`;
  const accessibleName = name ?? fallbackName;
  const className = [
    styles.chip,
    unavailable ? styles.chipUnavailable : undefined,
  ]
    .filter(Boolean)
    .join(" ");
  const source = label !== undefined && label !== "" ? label : citationId;
  const body = (
    <>
      {`[${String(index)}]`}
      {source !== undefined && source !== "" ? (
        <>
          {" "}
          <span className={styles.chipLabel}>
            <UserText value={source} />
          </span>
        </>
      ) : null}
      {unavailable && (label === undefined || label === "")
        ? ` — ${displayText("unavailable")}`
        : null}
    </>
  );
  if (href && !onSelect) {
    return (
      <a className={className} href={href} rel="noreferrer" aria-label={accessibleName}>
        {body}
      </a>
    );
  }
  return (
    <button
      type="button"
      className={className}
      onClick={(event) => onSelect?.(event.currentTarget)}
      aria-label={accessibleName}
    >
      {body}
    </button>
  );
}
