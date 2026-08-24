/**
 * Ask workspace layout wrapper.
 */

import type { ReactNode } from "react";
import styles from "./chat.module.css";

export type ChatWorkspaceProps = {
  /** Conversation rail or mobile placeholder. */
  rail: ReactNode;
  /** Answer column. */
  stage: ReactNode;
  /** Optional sources column at 1440px. */
  sources?: ReactNode;
  /** Compact conversation/sources triggers for narrow viewports. */
  toolbar?: ReactNode;
};

/**
 * Render the Ask grid.
 *
 * @param props - Rail, stage, optional sources and toolbar.
 * @returns Workspace grid.
 */
export function ChatWorkspace({
  rail,
  stage,
  sources,
  toolbar,
}: ChatWorkspaceProps) {
  return (
    <div>
      {toolbar}
      <div className={styles.workspace}>
        {rail}
        {stage}
        {sources}
      </div>
    </div>
  );
}
