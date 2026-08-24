/**
 * Run pipeline progress. Five known stages only.
 */

import type { ChatViewState } from "../../lib/chat-view";
import styles from "./chat.module.css";

const PIPELINE_STEPS = [
  { id: "preparing", label: "Preparing" },
  { id: "retrieving", label: "Retrieving" },
  { id: "generating", label: "Generating" },
  { id: "verifying", label: "Verifying" },
] as const;

export type RunProgressProps = {
  /** Current chat view. */
  chat: ChatViewState;
};

/**
 * Render expanded stages while running, then a collapsed status row.
 *
 * @param props - Chat view.
 * @returns Pipeline list or collapsed status.
 */
export function RunProgress({ chat }: RunProgressProps) {
  const raw = (chat.stage ?? "").toLowerCase();
  const stage =
    raw.includes("verif") ? "verifying"
    : raw.includes("generat") || raw.includes("answer") ? "generating"
    : raw.includes("retriev") || raw.includes("search") ? "retrieving"
    : raw.includes("connect") || raw.includes("queue") || raw.includes("prepar") ? "preparing"
    : raw;
  if (chat.terminal !== null) {
    return (
      <p className={styles.pipelineCollapsed}>
        Run status
        {chat.stage ? ` · ${chat.stage}` : ""}
      </p>
    );
  }
  return (
    <ul className={styles.pipeline} aria-label="Run pipeline" aria-live="polite">
      {PIPELINE_STEPS.map((step) => (
        <li
          key={step.id}
          className={styles.pipelineStep}
          data-active={stage.includes(step.id)}
        >
          {step.label}
        </li>
      ))}
    </ul>
  );
}
