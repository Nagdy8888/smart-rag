import { parseCheckpointUsage, parseDisplayCost, type CheckpointUsage } from "../checkpoint-usage";
import { parseCostReporting, type CostReporting } from "../cost-reporting";
/** Anonymous admin aggregates; never includes conversation content. */
import type { ApiAuth } from "./headers";
import { resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";
import { throwIfNotOk } from "./errors";
import type { MaintenanceKind } from "./knowledge-maintenance";

export type OverviewPeriod = 7 | 30 | 90;
export type OutcomeKey = "supported" | "partial" | "insufficient_evidence" | "conflicting_evidence";
export type AuthorityKey = "approved" | "unreviewed" | "draft" | "superseded";
export type Overview = {
  generated_at: string; period_start: string; days: OverviewPeriod; timezone: "UTC"; reliability_enabled: boolean;
  summary: { questions: number; completed: number; failed: number; cancelled: number; measured: number; supported: number;
    not_measured: number; median_response_seconds: number | null; latency_samples: number; cost_usd: string; cost_reporting?: CostReporting | null; display_cost_usd?: string | null; checkpoint_usage?: CheckpointUsage | null };
  daily: { date: string; questions: number; cost_usd: string; cost_reporting?: CostReporting | null; display_cost_usd?: string | null }[];
  outcomes: Partial<Record<OutcomeKey, number>>; authority: Partial<Record<AuthorityKey, number>>;
  authority_unversioned: number; attention_counts: Partial<Record<MaintenanceKind, number>>;
  attention_items: { kind: MaintenanceKind; source_id: string; document_id: string | null; title: string | null }[];
};
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);
const count = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const cost = (value: unknown): value is string => typeof value === "string" && /^\d+(\.\d+)?$/.test(value) && Number.isFinite(Number(value));
const kinds = ["missing_owner", "overdue_review", "feedback", "insufficient_evidence", "conflicting_evidence"];
/** Reject malformed measurements instead of silently presenting false zeros. */
export function parseOverview(value: unknown): Overview {
  if (!object(value) || !object(value.summary) || ![7,30,90].includes(value.days as number) || value.timezone !== "UTC" ||
    typeof value.reliability_enabled !== "boolean" || typeof value.generated_at !== "string" || !Number.isFinite(Date.parse(value.generated_at)) ||
    typeof value.period_start !== "string" || !Number.isFinite(Date.parse(value.period_start))) throw new Error("invalid_overview_response");
  const summary = value.summary;
  if (!["questions","completed","failed","cancelled","measured","supported","not_measured","latency_samples"].every(key=>count(summary[key])) ||
    !cost(summary.cost_usd) || !(summary.median_response_seconds === null || typeof summary.median_response_seconds === "number" && Number.isFinite(summary.median_response_seconds) && summary.median_response_seconds >= 0)) throw new Error("invalid_overview_response");
  if (!Array.isArray(value.daily) || value.daily.length !== value.days || !value.daily.every(day=>object(day) && typeof day.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(day.date) && count(day.questions) && cost(day.cost_usd))) throw new Error("invalid_overview_response");
  for (const [key, allowed] of [["outcomes",["supported","partial","insufficient_evidence","conflicting_evidence"]],["authority",["approved","unreviewed","draft","superseded"]],["attention_counts",kinds]] as const) {
    const record = value[key];
    if (!object(record) || !Object.entries(record).every(([name,n])=>(allowed as readonly string[]).includes(name) && count(n))) throw new Error("invalid_overview_response");
  }
  if (!count(value.authority_unversioned) || !Array.isArray(value.attention_items) || value.attention_items.length > 5 || !value.attention_items.every(item=>object(item) && kinds.includes(item.kind as string) && typeof item.source_id === "string" && (item.document_id === null || typeof item.document_id === "string") && (item.title === null || typeof item.title === "string"))) throw new Error("invalid_overview_response");
  parseCostReporting(summary.cost_reporting);
  for (const day of value.daily) parseCostReporting(day.cost_reporting);
  if (summary.display_cost_usd !== undefined) summary.display_cost_usd = parseDisplayCost(summary.display_cost_usd);
  if (summary.checkpoint_usage !== undefined) summary.checkpoint_usage = parseCheckpointUsage(summary.checkpoint_usage);
  for (const day of value.daily as Record<string,unknown>[]) if (day.display_cost_usd !== undefined) day.display_cost_usd = parseDisplayCost(day.display_cost_usd);
  return value as Overview;
}
export async function fetchOverview(auth: ApiAuth, days: OverviewPeriod): Promise<Overview> {
  const response = await fetch(apiUrl(`/admin/overview?days=${days}`), { headers: resumeHeaders(auth), cache: "no-store" });
  if (!response.ok) throwIfNotOk(response, await readJsonObject(response));
  return parseOverview(await response.json());
}
