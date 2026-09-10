/**
 * Human citation locators. Page/title/section only; never passage text.
 */

import { displayText } from "./safe-text";
import type { CitationResponse } from "./types";

export type CitationLocatorField = {
  /** Stable field id for tests and keys. */
  key: string;
  /** Visible label. */
  label: string;
  /** Untrusted display value. */
  value: string;
};

/**
 * Return a finite page number from provenance, or null.
 *
 * @param value - `page_number` or `page` candidate.
 * @returns 1-based file page, or null when missing.
 */
export function citationPageNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

/**
 * Return the printed PDF page label when present.
 *
 * @param value - `page_label` candidate.
 * @returns Printed label such as `179` or `vii`, or empty.
 */
export function citationPageLabel(value: unknown): string {
  return locatorString(value);
}

/**
 * Return the page string users should open in the original file.
 *
 * Prefers the PDF `/PageLabels` value (printed roman or arabic) over the
 * 1-based file index. File index is a fallback when the PDF has no labels.
 *
 * @param provenance - Citation provenance mapping.
 * @returns Printed or file page text, or empty.
 */
export function citationDisplayPage(
  provenance: Record<string, unknown>,
): string {
  const printed = citationPageLabel(provenance.page_label);
  if (printed) {
    return printed;
  }
  const filePage = citationPageNumber(provenance.page_number ?? provenance.page);
  return filePage === null ? "" : String(filePage);
}

/**
 * Return the last heading from a section path.
 *
 * @param value - Array or slash-delimited path.
 * @returns Last non-empty heading, or empty.
 */
export function citationHeading(value: unknown): string {
  const parts = citationSectionParts(value);
  return parts[parts.length - 1] ?? "";
}

/**
 * Return a chip label from locator provenance.
 *
 * Prefers document title, printed page, then heading or sheet/range. Falls
 * back to "Evidence" rather than a UUID. Unavailable sources stay labeled
 * as such.
 *
 * @param citation - Authorized citation row.
 * @returns Visible source label without passage text.
 */
export function citationSourceLabel(citation: CitationResponse): string {
  if (citation.source_unavailable) {
    return "Source unavailable";
  }
  const provenance = citation.provenance;
  const title = locatorString(provenance.document_title);
  const page = citationDisplayPage(provenance);
  const heading = citationHeading(provenance.section_path);
  const sheet = locatorString(provenance.sheet_name);
  const range = locatorString(provenance.range_ref);
  const parts: string[] = [];
  if (title) {
    parts.push(title);
  }
  if (page) {
    parts.push(`p. ${page}`);
  } else if (sheet) {
    parts.push(range ? `${sheet} ${range}` : sheet);
  }
  if (heading && (page || title || !sheet)) {
    if (!title || heading !== title) {
      parts.push(heading);
    }
  }
  if (parts.length === 0) {
    return "Evidence";
  }
  return parts.join(" · ");
}

/**
 * Return labeled locator rows for the sources drawer.
 *
 * Printed `page_label` is "Page". The 1-based file index is "PDF page" when
 * it differs from the printed label, or when no printed label exists.
 *
 * @param citation - Authorized citation row.
 * @returns Locator rows then technical ids. Omits empty values.
 */
export function citationLocatorFields(
  citation: CitationResponse,
): { locators: CitationLocatorField[]; technical: CitationLocatorField[] } {
  const provenance = citation.provenance;
  const locators: CitationLocatorField[] = [];
  const title = locatorString(provenance.document_title);
  const printed = citationPageLabel(provenance.page_label);
  const filePage = citationPageNumber(provenance.page_number ?? provenance.page);
  const section = citationSectionParts(provenance.section_path).join(" / ");
  const sheet = locatorString(provenance.sheet_name);
  const range = locatorString(provenance.range_ref);
  const url = locatorString(provenance.source_url ?? provenance.url);
  const ranges = Array.isArray(provenance.source_ranges)
    ? provenance.source_ranges.map(String).filter((item) => item.trim() !== "")
    : [];
  if (title) {
    locators.push({ key: "document_title", label: "Document", value: title });
  }
  if (printed) {
    locators.push({ key: "page_label", label: "Page", value: printed });
  }
  if (filePage !== null) {
    const fileText = String(filePage);
    if (!printed || printed !== fileText) {
      locators.push({
        key: "page_number",
        label: "PDF page",
        value: fileText,
      });
    }
  }
  if (section) {
    locators.push({ key: "section_path", label: "Section", value: section });
  }
  if (sheet) {
    locators.push({ key: "sheet_name", label: "Sheet", value: sheet });
  }
  if (range) {
    locators.push({ key: "range_ref", label: "Range", value: range });
  }
  if (ranges.length > 0) {
    locators.push({
      key: "source_ranges",
      label: "Ranges",
      value: ranges.join(", "),
    });
  }
  if (url) {
    locators.push({ key: "url", label: "URL", value: url });
  }
  const technical: CitationLocatorField[] = [
    { key: "citation_id", label: "Citation id", value: citation.citation_id },
  ];
  if (citation.chunk_id) {
    technical.push({
      key: "chunk_id",
      label: "Chunk id",
      value: citation.chunk_id,
    });
  }
  return { locators, technical };
}

/**
 * Accessible chip name. Keeps `Citation {index}` as the prefix.
 *
 * @param citation - Authorized citation row.
 * @returns Screen-reader name.
 */
export function citationChipName(citation: CitationResponse): string {
  const label = citationSourceLabel(citation);
  if (label === "Evidence") {
    return `Citation ${String(citation.citation_index)}`;
  }
  return `Citation ${String(citation.citation_index)}, ${displayText(label)}`;
}

function locatorString(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  return displayText(value).trim();
}

function citationSectionParts(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => displayText(String(item)).trim())
      .filter((item) => item !== "");
  }
  if (typeof value === "string" && value.trim() !== "") {
    return value
      .split("/")
      .map((item) => displayText(item).trim())
      .filter((item) => item !== "");
  }
  return [];
}
