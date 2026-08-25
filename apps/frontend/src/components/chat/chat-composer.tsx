/**
 * Sticky composer. Send becomes Cancel while a run is active.
 */

"use client";

import { COMPOSER_MAX_CHARS, composerDraftIsSendable } from "../../lib/composer";
import { Button } from "../ui/button";
import { Icon } from "../ui/icon";
import { StatusBanner } from "../ui/status-banner";
import { Textarea } from "../ui/textarea";
import styles from "./chat.module.css";

export type ChatComposerProps = {
  /** Draft text. */
  value: string;
  /** Draft change. */
  onChange: (value: string) => void;
  /** Send the draft. */
  onSend: () => void;
  /** Cancel the active run. */
  onCancel: () => void;
  /** Resume the current run stream. */
  onReconnect: () => void;
  /** Whether send is allowed. */
  sendDisabled: boolean;
  /** True while a run is in flight. */
  running: boolean;
  /** Accessible reason when Send is blocked. */
  sendBlockedReason?: string | null;
  /** Current automatic reconnect attempt (1-based), or 0. */
  reconnectAttempt?: number;
  /** Automatic reconnect ceiling. */
  reconnectMaxAttempts?: number;
  /** Milliseconds until the next automatic retry. */
  nextRetryMs?: number | null;
  /** True after automatic reconnect stops. */
  reconnectExhausted?: boolean;
};

/**
 * Render the Ask composer.
 *
 * @param props - Controlled draft and send/cancel/reconnect.
 * @returns Sticky composer. No attachments.
 */
export function ChatComposer({
  value,
  onChange,
  onSend,
  onCancel,
  onReconnect,
  sendDisabled,
  running,
  sendBlockedReason = null,
  reconnectAttempt = 0,
  reconnectMaxAttempts = 0,
  nextRetryMs = null,
  reconnectExhausted = false,
}: ChatComposerProps) {
  const remaining = COMPOSER_MAX_CHARS - value.length;
  return (
    <div className={styles.composer}>
      <Textarea
        label="Message"
        rows={3}
        maxLength={COMPOSER_MAX_CHARS}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Ask anything about your documents…"
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing || event.key !== "Enter" || event.shiftKey) {
            return;
          }
          event.preventDefault();
          if (!running && !sendDisabled) {
            onSend();
          }
        }}
      />
      <p className={styles.hint}>
        {remaining} characters remaining. Enter sends, Shift+Enter adds a line.
        Attachments are not accepted here.
      </p>
      <div className={styles.composerActions}>
        {running ? (
          <Button
            type="button"
            variant="secondary"
            data-action-id="ask.cancel"
            onClick={onCancel}
          >
            Stop
          </Button>
        ) : (
          <Button
            type="button"
            variant="primary"
            data-action-id="ask.send"
            onClick={onSend}
            disabled={sendDisabled || !composerDraftIsSendable(value)}
            aria-describedby={sendBlockedReason ? "chat-send-reason" : undefined}
          >
            <Icon name="send" />
            Send
          </Button>
        )}
        <Button type="button" variant="ghost" data-action-id="ask.reconnect" onClick={onReconnect}>
          {reconnectExhausted ? "Retry" : "Reconnect"}
        </Button>
      </div>
      {sendBlockedReason ? (
        <div id="chat-send-reason">
          <StatusBanner kind="warning" role="status">
            {sendBlockedReason}
          </StatusBanner>
        </div>
      ) : null}
      {running || reconnectAttempt > 0 || reconnectExhausted ? (
        <p className={styles.hint} role="status" data-testid="reconnect-status">
          {reconnectExhausted
            ? `Automatic reconnect stopped after ${String(reconnectMaxAttempts)} attempts. Partial output is kept. Use Retry.`
            : reconnectAttempt > 0
              ? `Reconnecting… attempt ${String(reconnectAttempt)} of ${String(reconnectMaxAttempts)}${
                  nextRetryMs !== null ? `. Next retry in ${String(nextRetryMs)} ms.` : ""
                }`
              : "Stop ends the run. Reconnect resumes the same run."}
        </p>
      ) : null}
    </div>
  );
}
