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
          >
            <Icon name="send" />
            Send
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={onReconnect}>
          Reconnect
        </Button>
      </div>
    </div>
  );
}
