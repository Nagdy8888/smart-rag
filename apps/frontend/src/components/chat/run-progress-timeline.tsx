/**
 * Truthful node and tool progress timeline. No percentages or clocks.
 */

"use client";

import { useState } from "react";
import type { ChatViewState } from "../../lib/chat-view";
import type { RunProgressItem } from "../../lib/run-progress";
import {
  EMPTY_DEADLINE_PARTIAL_COPY,
  isDeadlinePartialStatus,
} from "../../lib/run-details";
import { LiveRegion } from "../ui/live-region";
import { Spinner } from "../ui/spinner";
import { progressLabel, runStatusLine } from "./run-progress";
import styles from "./run-progress-timeline.module.css";

export type RunProgressTimelineProps = {
  items: readonly RunProgressItem[];
  terminal: ChatViewState["terminal"];
  verificationCompleted: boolean;
  answerAvailable: boolean;
  collapsed: boolean;
  /** Live chat view used only for the one-line summary. */
  chat?: ChatViewState | null;
  /** True while verified text is still being presented. */
  revealing?: boolean;
};

/**
 * Return the truthful one-line summary for the current progress phase.
 *
 * @param props - Timeline props.
 * @returns Status copy. Never a percentage or duration.
 */
export function progressSummary(props: RunProgressTimelineProps): string {
  if (props.terminal === "cancelled") {
    return props.answerAvailable
      ? "Cancelled"
      : "Cancelled. Received tokens are kept.";
  }
  if (props.terminal === "error") {
    return props.answerAvailable
      ? "Error"
      : "Something went wrong.";
  }
  if (props.terminal === "partial") {
    if (props.answerAvailable) {
      return "Partial";
    }
    if (isDeadlinePartialStatus(props.chat?.status)) {
      return EMPTY_DEADLINE_PARTIAL_COPY;
    }
    return "Partial answer. Verified tokens are kept.";
  }
  if (props.verificationCompleted && props.answerAvailable && props.collapsed) {
    return "Verified answer";
  }
  if (props.verificationCompleted && props.revealing) {
    return "Verified — displaying answer";
  }
  if (props.verificationCompleted && !props.answerAvailable) {
    return "Verified — preparing display";
  }
  if (props.chat) {
    return runStatusLine(props.chat) ?? progressLabel(props.items.at(-1)?.key ?? "prepare_query");
  }
  const current = [...props.items].reverse().find((item) => item.phase === "started");
  return progressLabel(current?.key ?? props.items.at(-1)?.key ?? "prepare_query");
}

/**
 * Render reducer items as an accessible progress list.
 *
 * @param props - Timeline items and reveal/terminal flags.
 * @returns Expanded list or a collapsed summary control.
 */
export function RunProgressTimeline(props: RunProgressTimelineProps) {
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const [collapsedSnap, setCollapsedSnap] = useState(props.collapsed);
  if (collapsedSnap !== props.collapsed) {
    setCollapsedSnap(props.collapsed);
    setUserOpen(null);
  }
  const open = userOpen ?? !props.collapsed;
  const summary = progressSummary(props);
  const showList = open && props.items.length > 0;
  return (
    <div className={styles.progressTimeline} data-testid="run-progress-timeline">
      <LiveRegion aria-label="Run progress" politeness="polite">
        <p className={styles.statusLine} role="status">
          {summary}
        </p>
      </LiveRegion>
      {props.items.length > 0 ? (
        <button
          type="button"
          className={styles.progressToggle}
          aria-expanded={showList}
          data-action-id="ask.expand_timeline"
          onClick={() => {
            setUserOpen(!open);
          }}
        >
          {showList ? "Hide steps" : "Show steps"}
        </button>
      ) : null}
      {showList ? (
        <ol className={styles.progressList} role="list">
          {props.items.map((item) => {
            const label = progressLabel(item.key);
            const active = item.phase === "started";
            return (
              <li
                key={item.id}
                className={styles.progressItem}
                role="listitem"
                aria-current={active ? "step" : undefined}
              >
                {active ? <Spinner label={label} /> : null}
                <span>
                  {label}
                  {item.phase === "failed" ? " failed" : item.phase === "completed" ? " done" : ""}
                </span>
                <span className={styles.progressKey}>{item.key}</span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </div>
  );
}
