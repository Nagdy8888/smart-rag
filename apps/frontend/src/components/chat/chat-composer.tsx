/**
 * Sticky composer. Send becomes Cancel while a run is active.
 */

"use client";

import { COMPOSER_MAX_CHARS, composerDraftIsSendable } from "../../lib/composer";
import { Button } from "../ui/button";
import { Icon } from "../ui/icon";
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
      />
      <p className={styles.hint}>
        {remaining} characters remaining. Enter sends only through the Send
        control. Attachments are not accepted here.
      </p>
      <div className={styles.composerActions}>
        {running ? (
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
        ) : (
          <Button
            type="button"
            variant="primary"
            onClick={onSend}
            disabled={sendDisabled || !composerDraftIsSendable(value)}
            aria-describedby={sendBlockedReason ? "chat-send-reason" : undefined}
          >
            <Icon name="send" />
            Send
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={onReconnect}>
          {reconnectExhausted ? "Retry" : "Reconnect"}
        </Button>
      </div>
      {sendBlockedReason ? (
        <p id="chat-send-reason" className={styles.hint} role="status">
          {sendBlockedReason}
        </p>
      ) : null}
      {running || reconnectAttempt > 0 || reconnectExhausted ? (
        <p className={styles.hint} role="status" data-testid="reconnect-status">
          {reconnectExhausted
            ? `Automatic reconnect stopped after ${String(reconnectMaxAttempts)} attempts. Partial output is kept. Use Retry.`
            : reconnectAttempt > 0
              ? `Reconnecting… attempt ${String(reconnectAttempt)} of ${String(reconnectMaxAttempts)}${
                  nextRetryMs !== null ? `. Next retry in ${String(nextRetryMs)} ms.` : ""
                }`
              : "Cancel stops the run. Reconnect resumes the same run."}
        </p>
      ) : null}
    </div>
  );
}
