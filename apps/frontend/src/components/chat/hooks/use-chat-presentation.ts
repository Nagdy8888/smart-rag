/** Layout preferences and verified-answer presentation for the Ask surface. */

"use client";

import { useEffect, useState } from "react";
import type { ChatViewState } from "../../../lib/chat-view";
import { useVerifiedAnswerReveal } from "./use-verified-answer-reveal";

/**
 * Keep media-query subscriptions and reveal state out of ChatApp composition.
 *
 * @param conversationId - Selected conversation.
 * @param chat - Authoritative run view.
 * @param animate - Whether this mount created the live run.
 * @returns Layout mode, stable presentation key, and reveal controls.
 */
export function useChatPresentation(
  conversationId: string | null,
  chat: ChatViewState,
  animate: boolean,
) {
  const [reducedMotion, setReducedMotion] = useState(false);
  const [compactAsk, setCompactAsk] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const compact = window.matchMedia("(max-width: 1279px)");
    const sync = (): void => {
      setReducedMotion(motion.matches);
      setCompactAsk(compact.matches);
    };
    sync();
    motion.addEventListener("change", sync);
    compact.addEventListener("change", sync);
    return () => {
      motion.removeEventListener("change", sync);
      compact.removeEventListener("change", sync);
    };
  }, []);
  const presentationKey = `${conversationId ?? "none"}:${chat.runId ?? "none"}`;
  const reveal = useVerifiedAnswerReveal({
    presentationKey,
    authoritativeText: chat.answerText,
    animate,
    reducedMotion,
  });
  return { compactAsk, presentationKey, reveal };
}
