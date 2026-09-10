/**
 * Untrusted-content helpers. React text nodes already escape HTML; these
 * helpers strip NULs, invert API `html.escape` entities, and reject
 * javascript: URLs so citations cannot become XSS vectors in `href`.
 */

const NUL = /\u0000/g;
const HTML_ESCAPE_ENTITY = /&(#x[0-9a-fA-F]+|#\d+|amp|lt|gt|quot|apos);/g;
const NAMED_HTML_ENTITIES: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
};

/**
 * Invert Python `html.escape(..., quote=True)` without using the DOM.
 *
 * @param text - API-escaped or raw text.
 * @returns Text with `&quot;`, `&amp;`, `&lt;`, `&gt;`, and `&#x27;` decoded.
 */
export function decodeHtmlEscapeEntities(text: string): string {
  return text.replace(HTML_ESCAPE_ENTITY, (matched, body: string) => {
    if (body.startsWith("#")) {
      const code =
        body[1] === "x" || body[1] === "X"
          ? Number.parseInt(body.slice(2), 16)
          : Number.parseInt(body.slice(1), 10);
      if (!Number.isFinite(code) || code < 0 || code > 0x10ffff) {
        return matched;
      }
      return String.fromCodePoint(code);
    }
    return NAMED_HTML_ENTITIES[body] ?? matched;
  });
}

/**
 * Normalize untrusted text for React text nodes.
 *
 * @param value - Model output, filename, entity label, or citation field.
 * @returns NUL-stripped text with API HTML entities decoded. Empty when the
 *   input is not a string.
 * @remarks
 * Security: still render through React text children. Decoding here only
 * undoes JSON-field HTML escaping so quotes display as quotes.
 */
export function displayText(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  return decodeHtmlEscapeEntities(value.replace(NUL, ""));
}

/**
 * Return whether a URL is safe to use as an `href` after authorization.
 *
 * @param value - Candidate URL from provenance or API.
 * @returns True only for http(s) URLs. `javascript:` and `data:` fail.
 */
export function isSafeHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

/**
 * Return a display string for a provenance coordinate without HTML.
 *
 * @param provenance - Server citation provenance mapping.
 * @returns Human-readable page/section/sheet/slide/URL labels.
 */
export function formatProvenance(provenance: Record<string, unknown>): string {
  const parts: string[] = [];
  const keys = [
    "document_title",
    "page",
    "page_label",
    "page_number",
    "section",
    "section_path",
    "sheet",
    "sheet_name",
    "slide",
    "range_ref",
    "url",
    "source_url",
  ] as const;
  for (const key of keys) {
    const raw = provenance[key];
    if (raw === undefined || raw === null) {
      continue;
    }
    if (Array.isArray(raw)) {
      parts.push(`${key}=${displayText(raw.map(String).join("/"))}`);
      continue;
    }
    parts.push(`${key}=${displayText(String(raw))}`);
  }
  return parts.join(" ");
}
