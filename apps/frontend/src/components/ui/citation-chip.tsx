/**
 * Citation index chip. List views must not show snippets.
 */

import { displayText } from "../../lib/safe-text";
import { UserText } from "./user-text";
import styles from "./ui.module.css";

export type CitationChipProps = {
  /** 1-based or server `citation_index`. */
  index: number;
  /** Optional citation id, rendered as isolated text. */
  citationId?: unknown;
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
 * Render `Citation {index}` as a chip.
 *
 * @param props - Index, optional id/href, unavailable flag.
 * @returns Anchor when `href` is set, otherwise a button or span.
 * @remarks
 * Security: `href` is not validated here. Do not pass `javascript:` URLs.
 * GAP-07-09 keeps production `href` null.
 */
export function CitationChip({
  index,
  citationId,
  unavailable = false,
  href = null,
  onSelect,
}: CitationChipProps) {
  const name = `Citation ${String(index)}`;
  const className = [
    styles.chip,
    unavailable ? styles.chipUnavailable : undefined,
  ]
    .filter(Boolean)
    .join(" ");
  const body = (
    <>
      {name}
      {citationId !== undefined && citationId !== "" ? (
        <>
          {" "}
          <UserText value={citationId} />
        </>
      ) : null}
      {unavailable ? ` — ${displayText("unavailable")}` : null}
    </>
  );
  if (href) {
    return (
      <a className={className} href={href} rel="noreferrer" aria-label={name}>
        {body}
      </a>
    );
  }
  return (
    <button
      type="button"
      className={className}
      onClick={(event) => onSelect?.(event.currentTarget)}
      aria-label={name}
    >
      {body}
    </button>
  );
}
