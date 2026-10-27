/** Reporting is independent of immutable budget accounting. */
export type CostReporting = {
  estimated_cost_usd: string | null;
  safety_allowance_usd: string;
  budget_accounted_usd: string;
  unresolved_operations: number;
  reconstructed_operations: number;
  estimated_operations: number;
  pricing_basis: string;
  measured_prompt_tokens?: number | null;
  measured_completion_tokens?: number | null;
  unmeasured_operations?: number;
};
export function parseCostReporting(value: unknown): CostReporting | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "object" || Array.isArray(value)) throw new Error("invalid_cost_reporting");
  const row=value as Record<string,unknown>;
  const money=(v:unknown)=>typeof v === "string" && /^\d+(\.\d+)?$/.test(v) && Number.isFinite(Number(v));
  if (!(row.estimated_cost_usd === null || money(row.estimated_cost_usd)) || !money(row.safety_allowance_usd) || !money(row.budget_accounted_usd) || typeof row.pricing_basis !== "string" ||
    ![row.unresolved_operations,row.reconstructed_operations,row.estimated_operations].every(v=>typeof v === "number" && Number.isSafeInteger(v) && v>=0)) throw new Error("invalid_cost_reporting");
  const count=(v:unknown)=>typeof v === "number" && Number.isSafeInteger(v) && v>=0;
  if (![row.measured_prompt_tokens,row.measured_completion_tokens].every(v=>v == null || count(v)) || !(row.unmeasured_operations === undefined || count(row.unmeasured_operations))) throw new Error("invalid_cost_reporting");
  return row as CostReporting;
}
