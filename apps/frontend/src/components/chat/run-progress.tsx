/**
 * Run pipeline progress. Five known stages only.
 */

import type { ChatViewState } from "../../lib/chat-view";
import styles from "./chat.module.css";

const PIPELINE_STEPS = [
  { id: "preparing", label: "Preparing" },
  { id: "searching", label: "Searching" },
  { id: "resolving", label: "Resolving graph" },
  { id: "reranking", label: "Reranking" },
  { id: "answering", label: "Answering" },
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
  const stage = (chat.stage ?? "").toLowerCase();
  if (chat.terminal !== null) {
    return (
      <p className={styles.pipelineCollapsed}>
        Run status
        {chat.stage ? ` · ${chat.stage}` : ""}
      </p>
    );
  }
  return (
    <ul className={styles.pipeline} aria-label="Run pipeline">
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
