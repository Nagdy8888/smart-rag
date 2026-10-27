/** Checked answer outcomes; unknown legacy values never imply support. */
export type KnowledgeResult = {
  outcome: "supported" | "partial" | "insufficient_evidence" | "conflicting_evidence";
  limitations: string[];
  unanswered_parts?: string[];
};

export const KNOWLEDGE_OUTCOME_LABELS = {
  supported: "Supported answer",
  partial: "Partial answer",
  insufficient_evidence: "Insufficient evidence",
  conflicting_evidence: "Conflicting evidence",
} as const;

/** Validate additive SSE and history metadata without inventing legacy labels. */
export function parseKnowledgeResult(value: unknown): KnowledgeResult | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if (typeof record.outcome !== "string" || !Object.hasOwn(KNOWLEDGE_OUTCOME_LABELS, record.outcome)) return null;
  if (!Array.isArray(record.limitations) || record.limitations.some((code) => typeof code !== "string")) return null;
  return { outcome: record.outcome as KnowledgeResult["outcome"], limitations: record.limitations.slice(0, 12),
    unanswered_parts: Array.isArray(record.unanswered_parts) ? record.unanswered_parts.filter((value): value is string => typeof value === "string").slice(0, 3) : [] };
}
