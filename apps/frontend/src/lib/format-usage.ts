/**
 * Display helpers for USD and token counts on Ask diagnostics.
 */

/**
 * Format a USD amount as a two-decimal currency string.
 *
 * @param value - Numeric amount or numeric string from the usage API.
 * @returns Example: `formatUsd(0.4)` → `"$0.40"`. Non-finite input returns `"—"`.
 */
export function formatUsd(value: number | string): string {
  const amount = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(amount)) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

/**
 * Format a token count with grouping and a `tokens` suffix.
 *
 * @param value - Token total.
 * @returns Example: `1234` → `"1,234 tokens"`.
 */
export function formatTokenCount(value: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  return `${new Intl.NumberFormat("en-US").format(value)} tokens`;
}

/**
 * Format prompt and completion tokens for Ask usage rows.
 *
 * @param promptTokens - Provider prompt tokens.
 * @param completionTokens - Provider completion tokens.
 * @returns Example: `412 prompt · 88 completion`. Null when both are zero.
 */
export function formatRunTokenUsage(
  promptTokens: number,
  completionTokens: number,
): string | null {
  if (!Number.isFinite(promptTokens) || !Number.isFinite(completionTokens)) {
    return null;
  }
  if (promptTokens <= 0 && completionTokens <= 0) {
    return null;
  }
  const grouping = new Intl.NumberFormat("en-US");
  return `${grouping.format(promptTokens)} prompt · ${grouping.format(completionTokens)} completion`;
}
