/**
 * Signed-out, revoked, and session-restoring Ask shells.
 */

"use client";

import Link from "next/link";
import { SESSION_REVOKED_BANNER } from "../../lib/auth/copy";
import { StatusBanner } from "../ui/status-banner";
import { Skeleton } from "../ui/skeleton";
import { ChatWorkspace } from "./chat-workspace";
import { ConversationRail } from "./conversation-rail";
import pageStyles from "./chat.module.css";
import transcriptStyles from "./chat-transcript.module.css";

const chatStyles = { ...pageStyles, ...transcriptStyles };

export type ChatSessionGateProps = {
  sessionsExpanded: boolean;
  onToggleExpanded: () => void;
};

/**
 * Render the restoring-session workspace.
 *
 * @param props - Sessions column visibility.
 * @returns Loading shell.
 */
export function ChatRestoringGate({
  sessionsExpanded,
  onToggleExpanded,
}: ChatSessionGateProps) {
  return (
    <div className={chatStyles.page}>
      <ChatWorkspace
        rail={
          <ConversationRail
            conversations={[]}
            selectedId={null}
            loading
            onCreate={() => undefined}
            onSelect={() => undefined}
            onDelete={() => undefined}
            expanded={sessionsExpanded}
            onToggleExpanded={onToggleExpanded}
            showCollapseToggle
          />
        }
        stage={
          <section className={chatStyles.stage} aria-label="Answer">
            <div className={chatStyles.conversation}>
              <Skeleton label="Restoring session" width="100%" />
              <Skeleton label="Restoring answer" width="80%" />
            </div>
          </section>
        }
        sessionsExpanded={sessionsExpanded}
      />
    </div>
  );
}

/**
 * Render the signed-out Ask prompt.
 *
 * @returns Sign-in banner.
 */
export function ChatSignedOutGate() {
  return (
    <div className={chatStyles.page}>
      <StatusBanner kind="info" role="status">
        Sign in to continue.
      </StatusBanner>
      <p className={chatStyles.muted}>
        <Link href="/login">Sign in</Link>
      </p>
    </div>
  );
}

/**
 * Render the revoked-session Ask prompt.
 *
 * @returns Safe revoked banner.
 */
export function ChatRevokedGate() {
  return (
    <div className={chatStyles.page}>
      <StatusBanner kind="error" role="alert">
        {SESSION_REVOKED_BANNER}
      </StatusBanner>
      <p className={chatStyles.muted}>
        <Link href="/login">Sign in</Link>
      </p>
    </div>
  );
}
