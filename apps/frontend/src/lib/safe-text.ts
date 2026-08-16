/**
 * Untrusted-content helpers. React text nodes already escape HTML; these
 * helpers strip NULs and reject javascript: URLs so citations cannot become
 * XSS vectors in `href`.
 */

const NUL = /\u0000/g;

/**
 * Normalize untrusted text for React text nodes.
 *
 * @param value - Model output, filename, entity label, or citation field.
 * @returns NUL-stripped text. Empty when the input is not a string.
 */
export function displayText(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  return value.replace(NUL, "");
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
  for (const key of ["page", "section", "sheet", "slide", "url"] as const) {
    const raw = provenance[key];
    if (raw === undefined || raw === null) {
      continue;
    }
    parts.push(`${key}=${displayText(String(raw))}`);
  }
  return parts.join(" ");
}
