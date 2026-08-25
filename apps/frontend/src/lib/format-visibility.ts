/**
 * Human labels for document visibility enums and absent status cells.
 */

const VISIBILITY_LABELS: Record<string, string> = {
  company_visible: "Company visible",
  company: "Company",
  private: "Private",
  restricted: "Restricted",
};

/**
 * Map a stored visibility enum to sentence-case chrome.
 *
 * @param value - API visibility string such as `company_visible`.
 * @returns Display label. Unknown snake_case values are title-cased.
 */
export function formatVisibility(value: string): string {
  const mapped = VISIBILITY_LABELS[value];
  if (mapped !== undefined) {
    return mapped;
  }
  return value
    .split("_")
    .filter((part) => part !== "")
    .map((part, index) =>
      index === 0 ? part.charAt(0).toUpperCase() + part.slice(1) : part,
    )
    .join(" ");
}

/**
 * Label used when a search/graph status cell has no loaded value.
 *
 * @param kind - `index` for missing projection, `pending` for in-flight gaps.
 * @returns `Not indexed` or `Pending`.
 */
export function absentStatusLabel(kind: "index" | "pending" = "index"): string {
  return kind === "pending" ? "Pending" : "Not indexed";
}
