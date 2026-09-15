/**
 * Human citation locators. Page/title/section only; never passage text.
 *
 * Company PDF chips use typed `document_title` and `pdf_page_number`. They
 * never call `citationDisplayPage()` or printed `page_label`.
 */

import { displayText } from "./safe-text";
import type { CitationResponse } from "./types";

/** Footer copy for citations that are not mapped to a verified paragraph. */
export const LEGACY_RUN_SOURCES_LABEL =
  "Legacy run sources (not mapped to a paragraph)";

/** Drawer copy when an authorized row has no stored paragraph span. */
export const LEGACY_EXCERPT_COPY =
  "Paragraph-level source text was not recorded for that run.";

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
 * Company PDF chips must not call this helper.
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
 * Split verified answer text on blank lines. Do not trim paragraphs.
 *
 * @param answerText - Authoritative verified answer.
 * @returns Paragraph strings, or empty when the answer is empty.
 */
export function splitVerifiedParagraphs(answerText: string): string[] {
  if (answerText === "") {
    return [];
  }
  return answerText.split("\n\n");
}

/**
 * Return whether this row is a company PDF (not web, not a sheet).
 *
 * @param citation - Authorized citation row.
 * @returns True when chips must use typed PDF page fields.
 */
export function isCompanyPdfCitation(citation: CitationResponse): boolean {
  const kind = citation.source_kind ?? "company_document";
  if (kind === "web") {
    return false;
  }
  return locatorString(citation.provenance.sheet_name) === "";
}

/**
 * Return the typed PDF toolbar page, or `unavailable`.
 *
 * @param citation - Authorized citation row.
 * @returns Decimal page text. Never printed `page_label`.
 */
export function pdfPageDisplay(citation: CitationResponse): string {
  const page = citation.pdf_page_number;
  if (typeof page === "number" && Number.isInteger(page) && page >= 1) {
    return String(page);
  }
  return "unavailable";
}

/**
 * Return the typed book/source title, or `Source`.
 *
 * @param citation - Authorized citation row.
 * @returns Display title from the typed field only.
 */
export function companyPdfBookTitle(citation: CitationResponse): string {
  const title = locatorString(citation.document_title);
  return title === "" ? "Source" : title;
}

/**
 * Return citations mapped to one verified paragraph.
 *
 * @param citations - Authorized citation rows.
 * @param paragraphIndex - 0-based paragraph.
 * @returns Rows whose `paragraph_index` equals the paragraph.
 */
export function citationsForParagraph(
  citations: readonly CitationResponse[],
  paragraphIndex: number,
): CitationResponse[] {
  return citations.filter((item) => item.paragraph_index === paragraphIndex);
}

/**
 * Return citations that must not attach to a rendered paragraph.
 *
 * @param citations - Authorized citation rows.
 * @param paragraphCount - Number of `\n\n`-split paragraphs.
 * @returns Null-index rows and mappings past the last paragraph.
 */
export function unmappedCitations(
  citations: readonly CitationResponse[],
  paragraphCount: number,
): CitationResponse[] {
  return citations.filter((item) => {
    const index = item.paragraph_index;
    if (typeof index !== "number") {
      return true;
    }
    return index < 0 || index >= paragraphCount;
  });
}

/**
 * Return the drawer heading. Company PDFs never use printed `page_label`.
 *
 * @param citation - Authorized citation row.
 * @returns Visible dialog title.
 */
export function citationDrawerTitle(citation: CitationResponse): string {
  if (citation.source_unavailable) {
    return `Citation ${String(citation.citation_index)}`;
  }
  if (isCompanyPdfCitation(citation)) {
    return `${companyPdfBookTitle(citation)} — PDF page ${pdfPageDisplay(citation)}`;
  }
  const page = citationDisplayPage(citation.provenance);
  return page === ""
    ? `Citation ${String(citation.citation_index)}`
    : `Page ${page}`;
}

/**
 * Return a chip label from typed PDF fields or locator provenance.
 *
 * Company PDF chips are `<title> · PDF page N` and never call
 * `citationDisplayPage()`. Sheets and web keep the previous locators.
 * Unavailable sources stay labeled as such.
 *
 * @param citation - Authorized citation row.
 * @returns Visible source label without passage text.
 */
export function citationSourceLabel(citation: CitationResponse): string {
  if (citation.source_unavailable) {
    return "Source unavailable";
  }
  if (isCompanyPdfCitation(citation)) {
    return `${companyPdfBookTitle(citation)} · PDF page ${pdfPageDisplay(citation)}`;
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
 * Company PDFs use typed Book/source and PDF page. Printed `page_label` is
 * omitted for those rows. Unavailable citations omit stale locators.
 *
 * @param citation - Authorized citation row.
 * @returns Locator rows then technical ids. Omits empty values.
 */
export function citationLocatorFields(
  citation: CitationResponse,
): { locators: CitationLocatorField[]; technical: CitationLocatorField[] } {
  const technical = citationTechnicalFields(citation);
  if (citation.source_unavailable) {
    return { locators: [], technical };
  }
  if (isCompanyPdfCitation(citation)) {
    const locators: CitationLocatorField[] = [
      {
        key: "document_title",
        label: "Book/source",
        value: companyPdfBookTitle(citation),
      },
      {
        key: "pdf_page_number",
        label: "PDF page",
        value: pdfPageDisplay(citation),
      },
    ];
    const section = citationSectionParts(citation.provenance.section_path).join(
      " / ",
    );
    if (section) {
      locators.push({ key: "section_path", label: "Section", value: section });
    }
    return { locators, technical };
  }
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
  return { locators, technical };
}

/**
 * Return technical identity rows for the drawer.
 *
 * @param citation - Authorized citation row.
 * @returns Citation and chunk ids.
 */
function citationTechnicalFields(
  citation: CitationResponse,
): CitationLocatorField[] {
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
  return technical;
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
