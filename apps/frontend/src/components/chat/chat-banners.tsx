/**
 * Safe Ask failure and reconnect banners.
 */

"use client";

import type { ApiFailure } from "../../lib/api";
import {
  apiFailureBanner,
  chatRunFailureBanner,
  expectedRefusalCopy,
  GENERIC_PRODUCTION_ERROR,
} from "../../lib/failure-copy";
import { shouldShowChatFailureBanner, type ChatViewState } from "../../lib/chat-view";
import { MAX_RECONNECT_ATTEMPTS } from "../../lib/stream-reconnect";
import { LiveRegion } from "../ui/live-region";
import { StatusBanner } from "../ui/status-banner";

export type ChatBannersProps = {
  visibleFailure: ApiFailure | null;
  chat: ChatViewState;
  disconnected: boolean;
  reconnectAttempt: number;
  reconnectExhausted: boolean;
  nextRetryMs: number | null;
  feedbackStatus: string | null;
  deleteSuccess: boolean;
};

/**
 * Render handshake-safe banners and the assertive live region.
 *
 * @param props - Classified failures and reconnect counters.
 * @returns Banner stack. No fetch.
 */
export function ChatBanners({
  visibleFailure,
  chat,
  disconnected,
  reconnectAttempt,
  reconnectExhausted,
  nextRetryMs,
  feedbackStatus,
  deleteSuccess,
}: ChatBannersProps) {
  const showChatFailureBanner = shouldShowChatFailureBanner(chat);
  const refusalCopy = expectedRefusalCopy(
    chat.terminal,
    chat.status,
    chat.diagnostics.limitationCodes,
  );
  const assertiveCopy = (() => {
    if (visibleFailure?.kind === "upgrade" || visibleFailure?.kind === "budget") {
      return apiFailureBanner(visibleFailure);
    }
    if (refusalCopy !== null) {
      return refusalCopy;
    }
    if (showChatFailureBanner) {
      return GENERIC_PRODUCTION_ERROR;
    }
    return "";
  })();
  return (
    <>
      {visibleFailure ? (
        <StatusBanner
          kind={visibleFailure.kind === "deleted" ? "info" : "error"}
          role={visibleFailure.kind === "deleted" ? "status" : "alert"}
        >
          {apiFailureBanner(visibleFailure)}
        </StatusBanner>
      ) : null}
      {chat.failure !== null && showChatFailureBanner ? (
        <StatusBanner kind="error" role="alert">
          {chatRunFailureBanner(chat.failure, chat.runId)}
        </StatusBanner>
      ) : null}
      {disconnected && chat.terminal === null ? (
        <StatusBanner kind="warning" role="status">
          {reconnectExhausted
            ? `Automatic reconnect stopped after ${String(MAX_RECONNECT_ATTEMPTS)} attempts. Partial output is kept. Use Retry.`
            : reconnectAttempt > 0
              ? `Connection interrupted. Reconnecting… attempt ${String(reconnectAttempt)} of ${String(MAX_RECONNECT_ATTEMPTS)}${
                  nextRetryMs !== null ? `. Next retry in ${String(nextRetryMs)} ms.` : ""
                }`
              : "The stream disconnected. Automatic resume uses the same run. Use Reconnect if it does not recover."}
        </StatusBanner>
      ) : null}
      {feedbackStatus ? (
        <StatusBanner kind="info" role="status">
          {feedbackStatus}
        </StatusBanner>
      ) : null}
      <LiveRegion politeness="assertive" aria-label="Blocking errors" visuallyHidden>
        {assertiveCopy || ""}
      </LiveRegion>
      {deleteSuccess && visibleFailure?.kind !== "deleted" ? (
        <StatusBanner kind="info" role="status">
          Conversation deleted. Reads, resume, and citations are denied. No
          source text is shown.
        </StatusBanner>
      ) : null}
    </>
  );
}
