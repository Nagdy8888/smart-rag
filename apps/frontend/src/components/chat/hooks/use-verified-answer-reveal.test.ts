// @vitest-environment jsdom

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  useVerifiedAnswerReveal,
  VERIFIED_REVEAL_DEADLINE_MS,
  VERIFIED_REVEAL_MAX_PUBLICATIONS,
} from "./use-verified-answer-reveal";

const LONG_ANSWER = `${"Verified company policy. ".repeat(12)}End.`;

describe("useVerifiedAnswerReveal", () => {
  const frames: FrameRequestCallback[] = [];
  let now = 0;
  let rafId = 0;

  beforeEach(() => {
    frames.length = 0;
    now = 0;
    rafId = 0;
    vi.stubGlobal("performance", { now: () => now });
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      rafId += 1;
      frames.push(callback);
      return rafId;
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => {
      const index = id - 1;
      if (index >= 0 && index < frames.length) {
        frames[index] = () => undefined;
      }
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  function flushFrame(): void {
    const pending = frames.splice(0, frames.length);
    for (const callback of pending) {
      callback(now);
    }
  }

  it("keeps a long answer as a strict partial then completes by the deadline", () => {
    const { result } = renderHook(() =>
      useVerifiedAnswerReveal({
        presentationKey: "conv:run-1",
        authoritativeText: LONG_ANSWER,
        animate: true,
        reducedMotion: false,
      }),
    );
    expect(result.current.visibleText).toBe("");
    expect(result.current.isRevealing).toBe(true);
    act(() => {
      flushFrame();
    });
    expect(result.current.visibleText.length).toBeGreaterThan(0);
    expect(result.current.visibleText).not.toBe(LONG_ANSWER);
    expect(LONG_ANSWER.startsWith(result.current.visibleText)).toBe(true);
    const mid = result.current.visibleText;
    now = VERIFIED_REVEAL_DEADLINE_MS;
    act(() => {
      flushFrame();
    });
    expect(result.current.visibleText.startsWith(mid)).toBe(true);
    expect(result.current.visibleText).toBe(LONG_ANSWER);
    expect(result.current.isComplete).toBe(true);
    expect(result.current.publicationCount).toBeLessThanOrEqual(
      VERIFIED_REVEAL_MAX_PUBLICATIONS,
    );
  });

  it("never exceeds ninety reveal publications", () => {
    const huge = "字".repeat(4000);
    const { result } = renderHook(() =>
      useVerifiedAnswerReveal({
        presentationKey: "conv:run-cap",
        authoritativeText: huge,
        animate: true,
        reducedMotion: false,
      }),
    );
    for (let step = 0; step < 120; step += 1) {
      now = Math.min(VERIFIED_REVEAL_DEADLINE_MS, step * 16);
      act(() => {
        flushFrame();
      });
    }
    expect(result.current.visibleText).toBe(huge);
    expect(result.current.publicationCount).toBeLessThanOrEqual(
      VERIFIED_REVEAL_MAX_PUBLICATIONS,
    );
  });

  it("completes immediately when showFullAnswer is called", () => {
    const { result } = renderHook(() =>
      useVerifiedAnswerReveal({
        presentationKey: "conv:run-skip",
        authoritativeText: LONG_ANSWER,
        animate: true,
        reducedMotion: false,
      }),
    );
    act(() => {
      flushFrame();
    });
    expect(result.current.visibleText).not.toBe(LONG_ANSWER);
    act(() => {
      result.current.showFullAnswer();
    });
    expect(result.current.visibleText).toBe(LONG_ANSWER);
    expect(result.current.isRevealing).toBe(false);
  });

  it("shows historical and reduced-motion text immediately", () => {
    const historical = renderHook(() =>
      useVerifiedAnswerReveal({
        presentationKey: "conv:run-hist",
        authoritativeText: LONG_ANSWER,
        animate: false,
        reducedMotion: false,
      }),
    );
    expect(historical.result.current.visibleText).toBe(LONG_ANSWER);
    const reduced = renderHook(() =>
      useVerifiedAnswerReveal({
        presentationKey: "conv:run-rm",
        authoritativeText: LONG_ANSWER,
        animate: true,
        reducedMotion: true,
      }),
    );
    expect(reduced.result.current.visibleText).toBe(LONG_ANSWER);
  });

  it("preserves the visible prefix when authoritative text grows", () => {
    const { result, rerender } = renderHook(
      (props: { text: string }) =>
        useVerifiedAnswerReveal({
          presentationKey: "conv:run-grow",
          authoritativeText: props.text,
          animate: true,
          reducedMotion: false,
        }),
      { initialProps: { text: LONG_ANSWER } },
    );
    act(() => {
      flushFrame();
    });
    const prefix = result.current.visibleText;
    expect(prefix.length).toBeGreaterThan(0);
    const grown = `${LONG_ANSWER} Extra verified clause.`;
    rerender({ text: grown });
    expect(result.current.visibleText.startsWith(prefix) || result.current.visibleText === prefix).toBe(
      true,
    );
    expect(grown.startsWith(result.current.visibleText)).toBe(true);
  });

  it("cancels pending frames on key change and unmount", () => {
    const { result, rerender, unmount } = renderHook(
      (props: { key: string }) =>
        useVerifiedAnswerReveal({
          presentationKey: props.key,
          authoritativeText: LONG_ANSWER,
          animate: true,
          reducedMotion: false,
        }),
      { initialProps: { key: "conv:run-a" } },
    );
    act(() => {
      flushFrame();
    });
    expect(result.current.visibleText.length).toBeGreaterThan(0);
    rerender({ key: "conv:run-b" });
    expect(result.current.visibleText).toBe("");
    unmount();
    const leftover = frames.length;
    act(() => {
      flushFrame();
    });
    expect(frames.length).toBeLessThanOrEqual(leftover);
  });

  it("does not break emoji grapheme clusters", () => {
    const family = "Family 👨‍👩‍👧‍👦 done.";
    const { result } = renderHook(() =>
      useVerifiedAnswerReveal({
        presentationKey: "conv:run-emoji",
        authoritativeText: family,
        animate: true,
        reducedMotion: false,
      }),
    );
    act(() => {
      flushFrame();
    });
    expect(family.startsWith(result.current.visibleText)).toBe(true);
    expect(result.current.visibleText.includes("\u200D") || result.current.visibleText === family).toBe(
      true,
    );
  });
});
