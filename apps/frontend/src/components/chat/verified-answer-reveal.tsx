/**
 * Present verified answer text with a skip control. No HTML interpolation.
 */

"use client";

import { useState } from "react";
import { Button } from "../ui/button";
import { LiveRegion } from "../ui/live-region";
import { UserText } from "../ui/user-text";
import styles from "./chat-transcript.module.css";

export type VerifiedAnswerRevealProps = {
  /** Conversation + run presentation key. */
  presentationKey: string;
  /** Currently visible verified prefix. */
  visibleText: string;
  /** True while this session is still presenting the prefix. */
  isRevealing: boolean;
  /** True once authoritative verified text is non-empty. */
  authoritativeReady: boolean;
  /** Complete the reveal immediately. */
  onShowFull: () => void;
};

/**
 * Render the live assistant prefix and announce readiness once.
 *
 * @param props - Visible prefix, skip handler, and announcement flag.
 * @returns Safe text nodes. Answer slices are not a live region.
 */
export function VerifiedAnswerReveal({
  presentationKey,
  visibleText,
  isRevealing,
  authoritativeReady,
  onShowFull,
}: VerifiedAnswerRevealProps) {
  const [announcedKey, setAnnouncedKey] = useState<string | null>(null);
  if (authoritativeReady && announcedKey !== presentationKey) {
    setAnnouncedKey(presentationKey);
  }
  const announce = authoritativeReady && announcedKey === presentationKey;

  return (
    <div data-testid="verified-answer-reveal">
      {announce ? (
        <LiveRegion
          aria-label="Verified answer"
          politeness="polite"
          visuallyHidden
        >
          Verified answer ready
        </LiveRegion>
      ) : null}
      {visibleText ? (
        <p
          className={styles.answerProse}
          dir="auto"
          onPointerDown={isRevealing ? onShowFull : undefined}
          onCopy={isRevealing ? onShowFull : undefined}
        >
          <UserText value={visibleText} />
        </p>
      ) : null}
      {isRevealing ? (
        <Button
          type="button"
          variant="ghost"
          data-action-id="ask.show_full_answer"
          onClick={onShowFull}
        >
          Show full answer
        </Button>
      ) : null}
    </div>
  );
}
