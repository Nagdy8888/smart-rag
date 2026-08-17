/**
 * Logical Unicode-codepoint citation highlighting.
 *
 * Offsets are indexes into `[...text]` / `Array.from(text)`, never visual
 * order and never UTF-16 `String.prototype.slice` indexes. The citations
 * HTTP contract has no offset fields (GAP-07-09); this helper is the
 * reviewed fixture path, not an invented API.
 */

/** Canonical mixed-direction fixture from `STITCH_BRIEF.md`. */
export const CITATION_LOGICAL_FIXTURE_TEXT = "الشركة ACME وقعت العقد.";

/**
 * Exclusive-end codepoint range that must select `ACME` in the fixture.
 * Brief: offsets 7–11.
 */
export const CITATION_LOGICAL_START = 7;

/** Exclusive end of the ACME range. */
export const CITATION_LOGICAL_END = 11;

export type LogicalHighlightParts = {
  /** Codepoints before the range. */
  before: string;
  /** Codepoints in `[start, end)`. */
  match: string;
  /** Codepoints after the range. */
  after: string;
};

/**
 * Slice untrusted text by Unicode codepoint offsets.
 *
 * @param text - Canonical logical string. Non-strings become empty parts.
 * @param start - Inclusive codepoint index.
 * @param end - Exclusive codepoint index.
 * @returns `{ before, match, after }` joined from `[...text]`.
 * @remarks
 * Out-of-range indexes clamp. `start > end` yields an empty match at
 * `start`. Does not interpret HTML. Callers must render the parts as
 * React text nodes (a `<mark>` wrapper with text children is allowed).
 */
export function highlightLogicalRange(
  text: unknown,
  start: number,
  end: number,
): LogicalHighlightParts {
  const source = typeof text === "string" ? text : "";
  const points = Array.from(source);
  const length = points.length;
  const safeStart = Number.isFinite(start) ? Math.trunc(start) : 0;
  const safeEnd = Number.isFinite(end) ? Math.trunc(end) : 0;
  const lo = Math.min(Math.max(safeStart, 0), length);
  const hi = Math.min(Math.max(safeEnd, lo), length);
  return {
    before: points.slice(0, lo).join(""),
    match: points.slice(lo, hi).join(""),
    after: points.slice(hi).join(""),
  };
}
