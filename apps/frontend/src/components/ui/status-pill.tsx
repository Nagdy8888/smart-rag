/**
 * Lifecycle status pill. Callers map server enums; this component does not
 * invent statuses.
 */

import { UserText } from "./user-text";
import styles from "./ui.module.css";

export type StatusTone = "neutral" | "success" | "warning" | "danger";

export type StatusPillProps = {
  /** Server enum or label. Never inferred here. */
  status: unknown;
  /** Caller-selected tone. Default `neutral`. */
  tone?: StatusTone;
};

const TONE_CLASS: Record<StatusTone, string | undefined> = {
  neutral: undefined,
  success: styles.pillSuccess,
  warning: styles.pillWarning,
  danger: styles.pillDanger,
};

/**
 * Render a document or job status as isolated text.
 *
 * @param props - Mapped enum plus optional tone.
 * @returns Span. Hiding a pill does not mean the server denied the job.
 */
export function StatusPill({ status, tone = "neutral" }: StatusPillProps) {
  const toneClass = TONE_CLASS[tone];
  const combined = [styles.pill, toneClass].filter(Boolean).join(" ");
  return (
    <span className={combined}>
      <UserText value={status} />
    </span>
  );
}
