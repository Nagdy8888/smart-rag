/**
 * Pure Evaluation labels, tones, and dirty-state helpers. No fetch side effects.
 */

import { evalApproveBlockedReason } from "../../lib/eval-workspace";
import type { PdfEvalCaseDetail, PdfEvalCaseSummary, PdfEvalStatus } from "../../lib/types";
import type { StatusTone } from "../ui/status-pill";

/** Local Evaluation task panel. */
export type EvaluationView = "overview" | "cases" | "results";

/** Ordered task views for the accessible tablist. */
export const EVALUATION_VIEWS: readonly EvaluationView[] = [
  "overview",
  "cases",
  "results",
];

/** Visible task-tab labels. */
export const EVALUATION_VIEW_LABELS: Record<EvaluationView, string> = {
  overview: "Overview",
  cases: "Review cases",
  results: "Exam results",
};

/** Known query-class display labels. Unknown values pass through unchanged. */
export const QUERY_CLASS_LABELS = {
  factual_definition: "Factual definition",
  exact_acronym: "Exact acronym",
  semantic_paraphrase: "Semantic paraphrase",
  multi_part: "Multi-part",
  section_scoped: "Section-scoped",
} as const;

/** Dataset filter options. Values match the case-list API. */
export const DATASET_FILTER_OPTIONS = [
  { value: "all", label: "All datasets" },
  { value: "development", label: "Development" },
  { value: "qualification", label: "Qualification" },
] as const;

/** Review-status filter options. Values match the case-list API. */
export const REVIEW_FILTER_OPTIONS = [
  { value: "all", label: "All review states" },
  { value: "draft", label: "Draft" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
] as const;

/** Client-side source-status filter options. */
export const SOURCE_FILTER_OPTIONS = [
  { value: "all", label: "All source states" },
  { value: "current", label: "Current sources" },
  { value: "stale", label: "Stale sources" },
] as const;

/** Overview guidance branch from workspace counts. */
export type OverviewGuidanceKind = "empty" | "stale" | "drafts" | "ready";

/**
 * Return a friendly query-class label, or the original token when unknown.
 *
 * @param value - Server query_class. Hostile.
 * @returns Display label. Render through `UserText`.
 */
export function queryClassLabel(value: string): string {
  if (value in QUERY_CLASS_LABELS) {
    return QUERY_CLASS_LABELS[value as keyof typeof QUERY_CLASS_LABELS];
  }
  return value;
}

/**
 * Return a friendly dataset label for a split token.
 *
 * @param split - Server split. Hostile when unknown.
 * @returns Display label. Render through `UserText` when unknown.
 */
export function datasetLabel(split: string): string {
  if (split === "development") {
    return "Development";
  }
  if (split === "qualification") {
    return "Qualification";
  }
  return split;
}

/**
 * Return a review-status label from summary fields.
 *
 * @param status - Server review_status.
 * @param humanApproved - Named human approval flag.
 * @returns Display label.
 */
export function reviewStatusLabel(status: string, humanApproved: boolean): string {
  if (status === "approved" || (humanApproved && status !== "rejected")) {
    return "Approved";
  }
  if (status === "rejected") {
    return "Rejected";
  }
  if (status === "draft" || status === "") {
    return "Draft";
  }
  return status;
}

/**
 * Map review status to a `StatusPill` tone. Color is never the only signal.
 *
 * @param status - Server review_status.
 * @param humanApproved - Named human approval flag.
 * @returns Tone.
 */
export function reviewStatusTone(status: string, humanApproved: boolean): StatusTone {
  const label = reviewStatusLabel(status, humanApproved);
  if (label === "Approved") {
    return "success";
  }
  if (label === "Rejected") {
    return "danger";
  }
  if (label === "Draft") {
    return "warning";
  }
  return "neutral";
}

/**
 * Return source freshness copy.
 *
 * @param stale - Server gold_stale flag.
 * @returns Display label.
 */
export function sourceStatusLabel(stale: boolean): string {
  return stale ? "Sources stale" : "Sources current";
}

/**
 * Map source freshness to a `StatusPill` tone.
 *
 * @param stale - Server gold_stale flag.
 * @returns Tone.
 */
export function sourceStatusTone(stale: boolean): StatusTone {
  return stale ? "warning" : "success";
}

/**
 * Return a count label for required sources.
 *
 * @param count - Saved gold_chunk_count.
 * @returns Display label such as `2 sources`.
 */
export function sourceCountLabel(count: number): string {
  return `${String(count)} ${count === 1 ? "source" : "sources"}`;
}

/**
 * Format an optional status count. Absent fields are an em dash, not invented zero.
 *
 * @param value - Optional API integer.
 * @returns Display text.
 */
export function metricCount(value: number | undefined): string {
  if (value === undefined) {
    return "—";
  }
  return String(value);
}

/**
 * Choose Overview guidance from workspace counts.
 *
 * @param status - Status payload, or undefined while unused.
 * @returns Guidance kind. Missing optional counts are not treated as zero.
 */
export function overviewGuidanceKind(
  status: PdfEvalStatus | undefined,
): OverviewGuidanceKind {
  if (status === undefined || status.case_count === 0) {
    return "empty";
  }
  if (typeof status.stale_gold_count === "number" && status.stale_gold_count > 0) {
    return "stale";
  }
  if (typeof status.draft_count === "number" && status.draft_count > 0) {
    return "drafts";
  }
  return "ready";
}

/**
 * Pick the next case to review: stale first, then draft, then the first row.
 *
 * @param items - Accumulated summaries. No questions.
 * @returns Next summary, or undefined when empty.
 */
export function nextReviewCase(
  items: readonly PdfEvalCaseSummary[],
): PdfEvalCaseSummary | undefined {
  return (
    items.find((item) => item.gold_stale) ??
    items.find((item) => item.review_status === "draft") ??
    items[0]
  );
}

/**
 * Split a textarea into trimmed non-empty lines.
 *
 * @param value - Editor field.
 * @returns Line items.
 */
export function parseEvalLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter((item) => item !== "");
}

/**
 * Return whether case-detail fields differ from the loaded row.
 *
 * @param input - Editor fields plus loaded detail.
 * @returns True when a details PATCH would change labels.
 */
export function evalDetailsDirty(input: {
  question: string;
  expectedAnswer: string;
  atomicFacts: string;
  requiredTerms: string;
  queryClass: string;
  detail: Pick<
    PdfEvalCaseDetail,
    "question" | "expected_answer" | "atomic_facts" | "required_terms" | "query_class"
  >;
}): boolean {
  return (
    input.question !== input.detail.question ||
    input.expectedAnswer !== input.detail.expected_answer ||
    input.queryClass !== input.detail.query_class ||
    parseEvalLines(input.atomicFacts).join("\n") !== input.detail.atomic_facts.join("\n") ||
    parseEvalLines(input.requiredTerms).join("\n") !== input.detail.required_terms.join("\n")
  );
}

/**
 * Return the Approve disabled reason with details-first priority.
 *
 * @param input - Dirty flags plus saved gold state.
 * @returns Accessible reason, or null when Approve is allowed.
 */
export function evalApproveUiReason(input: {
  detailsDirty: boolean;
  goldDirty: boolean;
  goldStale: boolean;
  goldCount: number;
}): string | null {
  if (input.detailsDirty) {
    return "Save case details before approval.";
  }
  const core = evalApproveBlockedReason({
    goldStale: input.goldStale,
    goldCount: input.goldCount,
    unsavedGold: input.goldDirty,
  });
  if (core === "Save gold before approval.") {
    return "Save source changes before approval.";
  }
  if (core !== null && core.includes("Stale gold")) {
    return "Remap required sources from current passages before approval. Stale sources cannot be approved.";
  }
  if (core !== null && core.includes("1–3")) {
    return "Select 1–3 current source passages before approval.";
  }
  return core;
}

/**
 * Return a sentence-case exam status label.
 *
 * @param status - Exam run status.
 * @returns Display label.
 */
export function examStatusLabel(status: string): string {
  if (status === "queued") {
    return "Queued";
  }
  if (status === "running") {
    return "Running";
  }
  if (status === "succeeded") {
    return "Succeeded";
  }
  if (status === "failed") {
    return "Failed";
  }
  if (status === "cancelled") {
    return "Cancelled";
  }
  return status;
}

/**
 * Return the official Recall@10 percentage for the scorecard.
 *
 * @param input - Hit count, case count, and optional stored ratio.
 * @returns Rounded percent.
 */
export function examRecallPercent(input: {
  hitCount: number;
  caseCount: number;
  ratio: number | null;
}): number {
  const ratio =
    input.ratio !== null
      ? input.ratio
      : input.caseCount === 0
        ? 0
        : input.hitCount / input.caseCount;
  return Math.round(ratio * 100);
}

/**
 * Format an exam completion timestamp for the scorecard.
 *
 * @param value - ISO timestamp, or null.
 * @returns UTC medium datetime, the original string when unparseable, or `unknown`.
 */
export function formatExamCompletedAt(value: string | null): string {
  if (!value) {
    return "unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date);
}
