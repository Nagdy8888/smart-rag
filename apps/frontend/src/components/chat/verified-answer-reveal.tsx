/**
 * Present verified answer text with a skip control. No HTML interpolation.
 */

"use client";

import { useState, type ReactNode } from "react";
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
  /** Optional paragraph renderer. Defaults to a single `UserText` block. */
  children?: ReactNode;
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
  children = null,
}: VerifiedAnswerRevealProps) {
  const [announcedKey, setAnnouncedKey] = useState<string | null>(null);
  if (authoritativeReady && announcedKey !== presentationKey) {
    setAnnouncedKey(presentationKey);
  }
  const announce = authoritativeReady && announcedKey === presentationKey;
  const body =
    children ??
    (visibleText ? (
      <p className={styles.answerProse} dir="auto">
        <UserText value={visibleText} />
      </p>
    ) : null);

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
      {body ? (
        <div
          onPointerDown={isRevealing ? onShowFull : undefined}
          onCopy={isRevealing ? onShowFull : undefined}
        >
          {body}
        </div>
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
