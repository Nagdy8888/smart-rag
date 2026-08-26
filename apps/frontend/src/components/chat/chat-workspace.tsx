/**
 * Ask workspace layout wrapper.
 */

import type { ReactNode } from "react";
import styles from "./chat-rail.module.css";

export type ChatWorkspaceProps = {
  /** Conversation rail or mobile placeholder. */
  rail: ReactNode;
  /** Answer column. */
  stage: ReactNode;
  /** Compact Sessions trigger for narrow viewports. */
  toolbar?: ReactNode;
  /** Desktop Sessions column visibility. */
  sessionsExpanded?: boolean;
};

/**
 * Render the Ask grid.
 *
 * @param props - Rail, stage, optional sources and toolbar.
 * @returns Height-bounded workspace whose Sessions list and conversation
 *   scroll independently.
 */
export function ChatWorkspace({
  rail,
  stage,
  toolbar,
  sessionsExpanded = true,
}: ChatWorkspaceProps) {
  return (
    <div className={styles.workspaceHost}>
      {toolbar}
      <div
        className={[
          styles.workspace,
          sessionsExpanded
            ? styles.workspaceSessionsExpanded
            : styles.workspaceSessionsCollapsed,
        ].join(" ")}
        data-sessions-expanded={sessionsExpanded ? "true" : "false"}
      >
        {rail}
        {stage}
      </div>
    </div>
  );
}
