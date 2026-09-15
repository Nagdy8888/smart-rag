/**
 * Labels and citation visibility for additive `answer_origin` events.
 *
 * Origin is never inferred from Hybrid/Combined/NoRetrieval route pills.
 */

import { displayText } from "./safe-text";
import { ANSWER_ORIGINS, type AnswerOrigin } from "./types";
import type { StatusTone } from "../components/ui/status-pill";

/** Exact mixed-scope clarification from the general-chat generator. */
export const MIXED_SCOPE_CLARIFICATION =
  "This question mixes general knowledge and company documents. Ask one general question or one document question so the answer source stays clear.";

const ORIGIN_LABELS: Record<AnswerOrigin, string> = {
  general_knowledge: "General knowledge",
  company_documents: "Company documents",
  user_supplied_text: "Your text",
  deterministic: "Assistant",
  ambiguous: "Needs clarification",
  web: "Web",
};

const ORIGIN_TONES: Record<AnswerOrigin, StatusTone> = {
  general_knowledge: "neutral",
  company_documents: "success",
  user_supplied_text: "neutral",
  deterministic: "neutral",
  ambiguous: "warning",
  web: "success",
};

/**
 * Return whether a value is a catalog answer origin.
 *
 * @param value - Untrusted origin string.
 * @returns True for the six catalog values.
 */
export function isAnswerOrigin(value: string): value is AnswerOrigin {
  return (ANSWER_ORIGINS as readonly string[]).includes(value);
}

/**
 * Return the operator-facing origin label.
 *
 * Unknown origins are isolated as text and never treated as HTML.
 *
 * @param origin - Catalog origin, unknown string, or null.
 * @returns Visible label, or null when the older server omitted origin.
 */
export function answerOriginLabel(origin: string | null): string | null {
  if (origin === null || origin.trim() === "") {
    return null;
  }
  if (isAnswerOrigin(origin)) {
    return ORIGIN_LABELS[origin];
  }
  return displayText(origin);
}

/**
 * Return the StatusPill tone for a catalog origin.
 *
 * @param origin - Catalog origin, unknown string, or null.
 * @returns Tone. Unknown and null stay neutral.
 */
export function answerOriginTone(origin: string | null): StatusTone {
  if (origin !== null && isAnswerOrigin(origin)) {
    return ORIGIN_TONES[origin];
  }
  return "neutral";
}

/**
 * Return whether citation chips may render for this origin.
 *
 * Null preserves older servers that never emitted `answer_origin`.
 * Known non-company, non-web origins and unknown values hide chips.
 *
 * @param origin - Stored origin, or null.
 * @returns True for `company_documents`, `web`, or a missing origin.
 */
export function shouldShowCitations(origin: string | null): boolean {
  if (origin === null || origin.trim() === "") {
    return true;
  }
  return origin === "company_documents" || origin === "web";
}
