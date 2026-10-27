"use client";

import { KNOWLEDGE_OUTCOME_LABELS, type KnowledgeResult } from "../../lib/knowledge-result";
import { limitationCopy } from "../../lib/limitations";
import { Icon } from "../ui/icon";
import styles from "../ui/styles/knowledge.module.css";

/** A durable outcome remains the same on live release and restored history. */
export function KnowledgeOutcome({ result: outcome }: { result?: KnowledgeResult | null }) {
  if (!outcome) return null;
  const statusIcon = outcome.outcome === "supported" ? "checkCircle" : outcome.outcome === "conflicting_evidence" ? "alert" : outcome.outcome === "partial" ? "partial" : "help";
  const tone = outcome.outcome === "supported" ? "success" : outcome.outcome === "conflicting_evidence" ? "danger" : "warning";
  return <div className={styles.outcome} aria-label="Knowledge outcome">
    <span className={styles.status} data-tone={tone}><Icon name={statusIcon} aria-hidden="true" />{KNOWLEDGE_OUTCOME_LABELS[outcome.outcome]}</span>
    <div className={styles.limitations}>{outcome.limitations.map((code) => <p key={code}>{limitationCopy(code)}</p>)}</div>
    {outcome.unanswered_parts?.length ? <div><p><strong>Not covered by this answer:</strong></p><ul>{outcome.unanswered_parts.map((part) => <li key={part} dir="auto">{part}</li>)}</ul></div> : null}
    {outcome.outcome === "insufficient_evidence" ? <p>Try a narrower question or ask a knowledge owner to add the relevant guidance.</p> : null}
  </div>;
}
