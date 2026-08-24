/**
 * Run details sheet. Closed by default. Diagnostics stay in the DOM for tests.
 */

"use client";

import { INFERENCE_LINKS_UNAVAILABLE } from "../../lib/citation-drawer";
import type { ChatViewState } from "../../lib/chat-view";
import { displayText } from "../../lib/safe-text";
import { Button } from "../ui/button";
import { Sheet } from "../ui/sheet";
import { UserText } from "../ui/user-text";
import styles from "./chat.module.css";

export type RunDetailsSheetProps = {
  /** Whether the sheet is open. */
  open: boolean;
  /** Close handler. */
  onClose: () => void;
  /** Open handler. */
  onOpen: () => void;
  /** Current view. */
  chat: ChatViewState;
  /** Company usage USD string. */
  companyUsd: string;
};

/**
 * Render diagnostics. The definition list stays mounted when the sheet is closed.
 *
 * @param props - Open state and chat diagnostics.
 * @returns Trigger, optional sheet, and always-mounted diagnostics list.
 */
export function RunDetailsSheet({
  open,
  onClose,
  onOpen,
  chat,
  companyUsd,
}: RunDetailsSheetProps) {
  const diagnostics = chat.diagnostics;
  const body = (
    <>
      <dl data-testid="advanced-diagnostics">
        <dt>Requested route</dt>
        <dd>
          <UserText value={diagnostics.requestedRoute ?? chat.routeFamily ?? "—"} />
        </dd>
        <dt>Effective route</dt>
        <dd>
          <UserText value={diagnostics.effectiveRoute ?? "—"} />
        </dd>
        <dt>Corrected route</dt>
        <dd>
          <UserText value={diagnostics.correctedRoute ?? "none"} />
        </dd>
        <dt>Correction reason</dt>
        <dd>
          <UserText value={diagnostics.correctionReason ?? "—"} />
        </dd>
        <dt>Cache</dt>
        <dd>
          <UserText value={diagnostics.cacheStatus ?? "—"} />
        </dd>
        <dt>Coverage</dt>
        <dd>
          {diagnostics.coverageScore === null
            ? "—"
            : String(diagnostics.coverageScore)}
        </dd>
        <dt>Tools</dt>
        <dd>
          <UserText
            value={diagnostics.toolKeys.map(displayText).join(", ") || "none"}
          />
        </dd>
        <dt>Heartbeats</dt>
        <dd>{String(diagnostics.heartbeatCount)}</dd>
        <dt>Unknown events</dt>
        <dd>{diagnostics.unknownEvents.join(", ") || "none (ignored)"}</dd>
        <dt>Stage</dt>
        <dd>
          <UserText value={chat.stage ?? "—"} /> /{" "}
          <UserText value={chat.status ?? "—"} />
        </dd>
        <dt>Terminal</dt>
        <dd>
          <UserText value={chat.terminal ?? "running"} />
        </dd>
      </dl>
      <p className={styles.muted}>{INFERENCE_LINKS_UNAVAILABLE}</p>
      <p className={styles.muted} data-testid="usage-strip">
        Usage {String(diagnostics.promptTokens)}/{String(diagnostics.completionTokens)}{" "}
        tokens. Company total {companyUsd} USD.
      </p>
    </>
  );
  return (
    <>
      <Button type="button" variant="ghost" onClick={onOpen}>
        Run details
      </Button>
      {open ? (
        <Sheet title="Run details" onClose={onClose}>
          {body}
        </Sheet>
      ) : (
        <div className={styles.srOnly}>{body}</div>
      )}
    </>
  );
}
