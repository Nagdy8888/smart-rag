/**
 * Present already-verified answer text without coupling to SSE chunking.
 */

"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { segmentVerifiedText } from "../../../lib/verified-answer-segment";

/** Hard cap on reveal-owned React publications for one answer. */
export const VERIFIED_REVEAL_MAX_PUBLICATIONS = 90;

/** Reveal deadline from the first non-empty verified availability, in ms. */
export const VERIFIED_REVEAL_DEADLINE_MS = 2500;

/** Answers at or below this grapheme count publish in one frame. */
const SHORT_GRAPHEME_LIMIT = 80;

export type VerifiedRevealInput = {
  /** Conversation ID + run ID. Never a secret. */
  presentationKey: string;
  /** Complete authoritative verified buffer. */
  authoritativeText: string;
  /** True only for a run created in this mounted session. */
  animate: boolean;
  /** `prefers-reduced-motion: reduce`. */
  reducedMotion: boolean;
};

export type VerifiedRevealResult = {
  visibleText: string;
  isRevealing: boolean;
  isComplete: boolean;
  /** Development and test diagnostics only. */
  publicationCount: number;
  showFullAnswer(): void;
};

type RevealBox = {
  key: string;
  visibleCount: number;
  publicationCount: number;
};

/**
 * Cancel a pending animation frame if one is scheduled.
 *
 * @param rafRef - Mutable rAF handle.
 */
function cancelScheduledFrame(rafRef: { current: number | null }): void {
  if (rafRef.current !== null) {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
  }
}

/**
 * Progressively publish verified text independently of protocol terminal.
 *
 * Presentation cursor is never persisted. SSE sequence and reducer state are
 * not modified. Unmount, key change, skip, and `showFullAnswer` cancel rAF.
 *
 * @param input - Presentation key, authoritative text, and motion flags.
 * @returns Visible prefix and skip control.
 */
export function useVerifiedAnswerReveal(
  input: VerifiedRevealInput,
): VerifiedRevealResult {
  const { presentationKey, authoritativeText, animate, reducedMotion } = input;
  const segments = useMemo(
    () => segmentVerifiedText(authoritativeText),
    [authoritativeText],
  );
  const [box, setBox] = useState<RevealBox>(() => ({
    key: presentationKey,
    visibleCount: 0,
    publicationCount: 0,
  }));
  if (box.key !== presentationKey) {
    setBox({ key: presentationKey, visibleCount: 0, publicationCount: 0 });
  }
  const visibleCount =
    box.key === presentationKey ? box.visibleCount : 0;
  const publicationCount =
    box.key === presentationKey ? box.publicationCount : 0;
  if (segments.length === 0 && (visibleCount !== 0 || publicationCount !== 0)) {
    setBox({ key: presentationKey, visibleCount: 0, publicationCount: 0 });
  } else if (
    segments.length > 0 &&
    (!animate || reducedMotion) &&
    visibleCount !== segments.length
  ) {
    setBox({
      key: presentationKey,
      visibleCount: segments.length,
      publicationCount,
    });
  }

  const rafRef = useRef<number | null>(null);
  const deadlineRef = useRef<number | null>(null);
  const visibleCountRef = useRef(visibleCount);
  const publicationCountRef = useRef(publicationCount);
  const segmentsRef = useRef(segments);
  useLayoutEffect(() => {
    visibleCountRef.current = visibleCount;
    publicationCountRef.current = publicationCount;
    segmentsRef.current = segments;
  }, [publicationCount, segments, visibleCount]);

  const showFullAnswer = useCallback(() => {
    cancelScheduledFrame(rafRef);
    const total = segmentsRef.current.length;
    visibleCountRef.current = total;
    setBox((current) => ({
      key: presentationKey,
      visibleCount: total,
      publicationCount: current.key === presentationKey ? current.publicationCount : 0,
    }));
  }, [presentationKey]);

  useEffect(() => {
    const total = segments.length;
    if (total === 0 || !animate || reducedMotion) {
      cancelScheduledFrame(rafRef);
      deadlineRef.current = null;
      return;
    }
    if (deadlineRef.current === null) {
      deadlineRef.current = performance.now() + VERIFIED_REVEAL_DEADLINE_MS;
    }
    const pastCap =
      publicationCountRef.current >= VERIFIED_REVEAL_MAX_PUBLICATIONS ||
      performance.now() >= (deadlineRef.current ?? 0);
    if (pastCap) {
      visibleCountRef.current = total;
      setBox({
        key: presentationKey,
        visibleCount: total,
        publicationCount: publicationCountRef.current,
      });
      return;
    }

    const tick = (now: number): void => {
      rafRef.current = null;
      const currentTotal = segmentsRef.current.length;
      if (currentTotal === 0) {
        return;
      }
      const remaining = currentTotal - visibleCountRef.current;
      const remainingMs = Math.max(0, (deadlineRef.current ?? now) - now);
      if (
        remaining <= 0 ||
        remainingMs <= 0 ||
        publicationCountRef.current >= VERIFIED_REVEAL_MAX_PUBLICATIONS
      ) {
        visibleCountRef.current = currentTotal;
        publicationCountRef.current = Math.min(
          VERIFIED_REVEAL_MAX_PUBLICATIONS,
          publicationCountRef.current + 1,
        );
        setBox({
          key: presentationKey,
          visibleCount: currentTotal,
          publicationCount: publicationCountRef.current,
        });
        return;
      }
      if (currentTotal <= SHORT_GRAPHEME_LIMIT && visibleCountRef.current === 0) {
        visibleCountRef.current = currentTotal;
        publicationCountRef.current += 1;
        setBox({
          key: presentationKey,
          visibleCount: currentTotal,
          publicationCount: publicationCountRef.current,
        });
        return;
      }
      const publicationsLeft = Math.max(
        1,
        VERIFIED_REVEAL_MAX_PUBLICATIONS - publicationCountRef.current,
      );
      const estimatedFramesLeft = Math.max(1, Math.ceil(remainingMs / 16));
      const batch = Math.max(
        1,
        Math.ceil(remaining / Math.min(publicationsLeft, estimatedFramesLeft)),
      );
      let next = Math.min(currentTotal, visibleCountRef.current + batch);
      if (
        publicationCountRef.current === 0 &&
        currentTotal > SHORT_GRAPHEME_LIMIT
      ) {
        next = Math.min(next, currentTotal - 1);
      }
      visibleCountRef.current = next;
      publicationCountRef.current += 1;
      setBox({
        key: presentationKey,
        visibleCount: next,
        publicationCount: publicationCountRef.current,
      });
      if (visibleCountRef.current < currentTotal) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelScheduledFrame(rafRef);
    };
  }, [animate, presentationKey, reducedMotion, segments]);

  useEffect(() => {
    return () => {
      cancelScheduledFrame(rafRef);
    };
  }, []);

  const visibleText = segments.slice(0, visibleCount).join("");
  const isComplete = segments.length === 0 || visibleCount >= segments.length;
  return {
    visibleText,
    isRevealing: !isComplete && animate && !reducedMotion,
    isComplete,
    publicationCount,
    showFullAnswer,
  };
}
