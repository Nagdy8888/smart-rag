/**
 * Sticky composer. Draft state lives here so typing does not re-render Ask.
 */

"use client";

import { memo, useEffect, useRef, useState } from "react";
import { COMPOSER_MAX_CHARS, composerDraftIsSendable } from "../../lib/composer";
import { Button } from "../ui/button";
import { Icon } from "../ui/icon";
import { StatusBanner } from "../ui/status-banner";
import { Textarea } from "../ui/textarea";
import styles from "./chat-composer.module.css";

export type ChatComposerProps = {
  /** Submit the current draft. Return false to keep the text. */
  onSubmit: (text: string) => boolean | void | Promise<boolean | void>;
  /** True when handshake or readiness blocks send. */
  disabled: boolean;
  /** True from click until admission or error. */
  sending: boolean;
  /** True while a run is in flight. */
  running: boolean;
  /** Cancel the active run. */
  onStop: () => void;
  /** Resume the current run stream. */
  onReconnect: () => void;
  /** Show the reconnect banner. */
  showReconnect: boolean;
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
  /** Optional preset from a prompt chip. */
  seedText?: string | null;
  /** Increment to re-apply `seedText`. */
  seedKey?: number;
};

/**
 * Render the Ask composer with colocated draft state.
 *
 * @param props - Submit, stop, reconnect, and pending flags only.
 * @returns Sticky composer card. No attachments.
 * @remarks
 * Render-isolation contract: parent must not pass stream token text or
 * other `chat` fields except the stable `sending`/`running` booleans and
 * reconnect flags. The field clears as soon as Send is accepted; a false
 * `onSubmit` result restores the draft.
 */
export const ChatComposer = memo(function ChatComposer({
  onSubmit,
  disabled,
  sending,
  running,
  onStop,
  onReconnect,
  showReconnect,
  sendBlockedReason = null,
  reconnectAttempt = 0,
  reconnectMaxAttempts = 0,
  nextRetryMs = null,
  reconnectExhausted = false,
  seedText = null,
  seedKey = 0,
}: ChatComposerProps) {
  const [draft, setDraft] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const admissionLock = useRef(false);
  const isSending = sending || submitting;
  const busy = isSending || running;
  useEffect(() => {
    if (seedText) {
      setDraft(seedText);
    }
  }, [seedText, seedKey]);

  const remaining = COMPOSER_MAX_CHARS - draft.length;
  const sendable = composerDraftIsSendable(draft);
  const rows = Math.min(8, Math.max(1, draft.split("\n").length));

  /**
   * Submit the draft immediately so the question is not duplicated in the
   * field while create/admit is in flight. Restore the snapshot if send
   * returns false (create or admission failed).
   */
  async function handleSubmit(): Promise<void> {
    if (running || sending || admissionLock.current || disabled || !sendable) {
      return;
    }
    const snapshot = draft;
    admissionLock.current = true;
    setSubmitting(true);
    setDraft("");
    try {
      const result = await onSubmit(snapshot);
      if (result === false) {
        setDraft((current) => current ? `${snapshot}\n\n${current}` : snapshot);
      }
    } catch {
      setDraft((current) => current ? `${snapshot}\n\n${current}` : snapshot);
    } finally {
      admissionLock.current = false;
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.composer}>
      {showReconnect ? (
        <StatusBanner kind="warning" role="status">
          {reconnectExhausted
            ? `Automatic reconnect stopped after ${String(reconnectMaxAttempts)} attempts. Partial output is kept. Use Retry.`
            : reconnectAttempt > 0
              ? `Reconnecting… attempt ${String(reconnectAttempt)} of ${String(reconnectMaxAttempts)}${
                  nextRetryMs !== null ? `. Next retry in ${String(nextRetryMs)} ms.` : ""
                }`
              : "The stream disconnected. Automatic resume uses the same run."}
          <Button
            type="button"
            variant="secondary"
            size="compact"
            data-action-id="ask.reconnect"
            onClick={onReconnect}
          >
            {reconnectExhausted ? "Retry" : "Reconnect"}
          </Button>
        </StatusBanner>
      ) : null}
      <div className={styles.composerCard} data-working={busy ? "true" : "false"}>
        <Textarea
          label="Message"
          hideLabel
          fullWidth
          rows={rows}
          maxLength={COMPOSER_MAX_CHARS}
          value={draft}
          className={styles.composerField}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={busy ? "Draft your next question while you wait..." : "What would you like to know?"}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing || event.key !== "Enter" || event.shiftKey) {
              return;
            }
            event.preventDefault();
            void handleSubmit();
          }}
        />
        <div className={styles.composerFooter}>
          {running ? (
            <Button
              type="button"
              variant="secondary"
              className={`${styles.composerSend} ${styles.composerStop}`}
              data-action-id="ask.cancel"
              onClick={onStop}
            >
              <span className={styles.stopMark} aria-hidden="true" />
              Stop
            </Button>
          ) : (
            <Button
              type="button"
              variant="primary"
              className={styles.composerSend}
              data-action-id="ask.send"
              aria-label={isSending ? "Sending…" : "Send"}
              onClick={() => {
                void handleSubmit();
              }}
              pending={isSending}
              pendingLabel="Sending…"
              disabled={disabled || !sendable}
              aria-describedby={sendBlockedReason ? "chat-send-reason" : undefined}
            >
              <span>Send</span>
              <Icon name="arrowUp" />
            </Button>
          )}
        </div>
      </div>
      <div className={styles.composerMeta}>
          {busy ? (
            <p className={styles.composerStatus} role="status">
              <span className={styles.statusDot} aria-hidden="true" />
              {running ? "Working on your answer" : "Sending your message"}
            </p>
          ) : (
            <p className={styles.composerHint}>
              <kbd>Enter</kbd> to send <span className={styles.desktopHint}> / <kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line</span>
            </p>
          )}
          {remaining < 1000 ? (
            <p className={styles.hint}>{`${String(remaining)} characters left`}</p>
          ) : null}
      </div>
      {sendBlockedReason ? (
        <div id="chat-send-reason">
          <StatusBanner kind="warning" role="status">
            {sendBlockedReason}
          </StatusBanner>
        </div>
      ) : null}
    </div>
  );
});
