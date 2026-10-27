/** Anonymous per-run checkpoint totals, distinct from provider measurements. */
export type CheckpointUsage = {
  runs: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: string | null;
  unpriced_runs: number;
  overlapping_ledger_runs: number;
  additional_prompt_tokens: number;
  additional_completion_tokens: number;
  additional_estimated_cost_usd: string | null;
  first_recorded_at: string | null;
  last_recorded_at: string | null;
};

export function parseCheckpointUsage(value: unknown): CheckpointUsage | null {
  if (value == null) return null;
  if (typeof value !== "object" || Array.isArray(value)) throw new Error("invalid_checkpoint_usage");
  const row = value as Record<string, unknown>;
  const result: Record<string, unknown> = {};
  for (const key of ["runs", "prompt_tokens", "completion_tokens", "unpriced_runs", "overlapping_ledger_runs", "additional_prompt_tokens", "additional_completion_tokens"]) {
    const count = row[key];
    if (typeof count !== "number" || !Number.isSafeInteger(count) || count < 0) throw new Error("invalid_checkpoint_usage");
    result[key] = count;
  }
  for (const key of ["estimated_cost_usd", "additional_estimated_cost_usd"]) result[key] = parseDisplayCost(row[key]);
  for (const key of ["first_recorded_at", "last_recorded_at"]) {
    const date = row[key];
    if (!(date === null || typeof date === "string" && Number.isFinite(Date.parse(date)))) throw new Error("invalid_checkpoint_usage");
    result[key] = date;
  }
  return result as CheckpointUsage;
}

export function parseDisplayCost(value: unknown): string | null {
  if (value === null) return null;
  if (typeof value !== "string" || !/^\d+(\.\d+)?$/.test(value) || !Number.isFinite(Number(value))) throw new Error("invalid_usage_cost");
  return value;
}

/** An explicit unknown combined total must not fall back to a budget allowance. */
export function usageDisplayCost(value: { display_cost_usd?: string | null; cost_reporting?: { estimated_cost_usd: string | null } | null }): string | null {
  return value.display_cost_usd === undefined ? value.cost_reporting?.estimated_cost_usd ?? null : value.display_cost_usd;
}
