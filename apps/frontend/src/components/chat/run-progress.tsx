/**
 * Map a live run stage to the one-line Ask status copy.
 */

import type { ChatViewState } from "../../lib/chat-view";

/** Exact production stage keys to friendly labels. */
export const STAGE_LABELS: Readonly<Record<string, string>> = {
  enforce_admission: "Admission",
  load_memory: "Memory",
  prepare_query: "Preparing query",
  compile_plan: "Planning",
  company_scope: "Company retrieval",
  general_scope: "General answer",
  mixed_scope: "Clarification",
  invalid_scope: "Invalid scope",
  apply_correction: "Correction",
  fuse_evidence: "Fusion",
  compose_tables: "Tables",
  disclose_optional_tools: "Optional tools",
  generate_answer: "Generating…",
  verify_answer: "Verifying…",
  web_scope: "Searching…",
  web_search: "Searching…",
  web_read: "Reading…",
};

/**
 * Return a deterministic label for a node or tool key.
 *
 * @param key - Exact catalog/stage key.
 * @returns Friendly label, or a safe fallback that still includes the key.
 */
export function progressLabel(key: string): string {
  return STAGE_LABELS[key] ?? `Working: ${key}`;
}

/**
 * Return the idle-hidden status line for an in-flight run.
 *
 * @param chat - Current view.
 * @returns Exactly one of Admission, Preparing…, Retrieving…, Searching…,
 *   Reading…, Generating…, Verifying…, or null when idle.
 */
export function runStatusLine(chat: ChatViewState): string | null {
  if (chat.terminal !== null || chat.runId === null) {
    return null;
  }
  const raw = (chat.stage ?? "").toLowerCase();
  if (raw.includes("admission")) {
    return "Admission";
  }
  if (raw.includes("web_search") || raw.includes("web_scope")) {
    return "Searching…";
  }
  if (raw.includes("web_read")) {
    return "Reading…";
  }
  if (raw.includes("verif")) {
    return "Verifying…";
  }
  if (raw.includes("generat") || raw.includes("answer")) {
    return "Generating…";
  }
  if (raw.includes("retriev") || raw.includes("search")) {
    return "Retrieving…";
  }
  return "Preparing…";
}
