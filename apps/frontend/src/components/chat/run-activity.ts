/** Public activity summaries derived from stage events, never model reasoning. */

import type { RunProgressItem } from "../../lib/run-progress";

const ACTIVITIES: Readonly<Record<string, string>> = {
  enforce_admission: "Getting your request ready.",
  load_memory: "Reading the conversation context for this question.",
  prepare_query: "Understanding your question and preparing the search.",
  compile_plan: "Choosing how to find the information you need.",
  company_scope: "Searching company documents for relevant passages.",
  general_scope: "Preparing a response using general knowledge.",
  mixed_scope: "Checking which part of the question needs clarification.",
  invalid_scope: "Checking whether this request can be answered.",
  apply_correction: "Reviewing whether the search needs refinement.",
  fuse_evidence: "Bringing the retrieved information together.",
  compose_tables: "Preparing any structured data needed for the answer.",
  disclose_optional_tools: "Checking which additional tools are available.",
  generate_answer: "Drafting your answer from the available context.",
  verify_answer: "Checking the draft before showing you the answer.",
  web_scope: "Searching the web for relevant information.",
  web_search: "Searching the web for relevant information.",
  web_read: "Reading the selected web sources.",
};

const LABELS: Readonly<Record<string, string>> = {
  enforce_admission: "Understanding your question",
  load_memory: "Understanding your question",
  prepare_query: "Understanding your question",
  compile_plan: "Understanding your question",
  company_scope: "Finding information",
  web_scope: "Finding information",
  web_search: "Finding information",
  web_read: "Finding information",
  apply_correction: "Refining the search",
  fuse_evidence: "Preparing your answer",
  compose_tables: "Preparing your answer",
  disclose_optional_tools: "Preparing your answer",
  general_scope: "Writing your answer",
  generate_answer: "Writing your answer",
  verify_answer: "Checking the answer",
  mixed_scope: "Clarifying your question",
  invalid_scope: "Checking your request",
};

type PublicActivity = {
  id: string;
  label: string;
  phase: RunProgressItem["phase"];
};

/** Fold adjacent internal stages into familiar activities, preserving retry order. */
export function publicActivities(
  items: readonly RunProgressItem[],
): PublicActivity[] {
  const groups: { id: string; label: string; items: RunProgressItem[] }[] = [];
  for (const item of items) {
    const label =
      LABELS[item.key] ??
      (item.kind === "tool" ? "Using a tool" : "Working on your request");
    const previous = groups.at(-1);
    if (previous?.label === label) {
      previous.items.push(item);
    } else {
      groups.push({ id: item.id, label, items: [item] });
    }
  }
  return groups.map((group) => ({
    id: group.id,
    label: group.label,
    phase: group.items.some((item) => item.phase === "started")
      ? "started"
      : group.items.some((item) => item.phase === "failed")
        ? "failed"
        : "completed",
  }));
}

/** Describe only currently open work. Unknown stages never expose their payloads. */
export function runActivity(items: readonly RunProgressItem[]): string {
  const current = [...items].reverse().find((item) => item.phase === "started");
  if (!current) {
    return "Waiting for the next progress update.";
  }
  return (
    ACTIVITIES[current.key] ??
    (current.kind === "tool"
      ? "Waiting for the current tool to finish."
      : "Working on your request.")
  );
}
