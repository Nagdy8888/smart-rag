// @vitest-environment node

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MAX_RECONNECT_ATTEMPTS,
  RECONNECT_DELAYS_MS,
  reconnectDelayMs,
  shouldStopReconnect,
  waitForReconnectDelay,
} from "./stream-reconnect";

describe("stream reconnect policy", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("uses three delays of 500, 1500, and 3000 ms", () => {
    expect(RECONNECT_DELAYS_MS).toEqual([500, 1500, 3000]);
    expect(MAX_RECONNECT_ATTEMPTS).toBe(3);
    expect(reconnectDelayMs(0)).toBe(500);
    expect(reconnectDelayMs(1)).toBe(1500);
    expect(reconnectDelayMs(2)).toBe(3000);
    expect(() => reconnectDelayMs(3)).toThrow(RangeError);
  });

  it("stops on cancel, terminal, sign-out, deleted run, unmount, and exhaustion", () => {
    const base = {
      attemptIndex: 0,
      cancelled: false,
      terminal: null as string | null,
      signedOut: false,
      runDeleted: false,
      unmounted: false,
    };
    expect(shouldStopReconnect(base)).toBeNull();
    expect(shouldStopReconnect({ ...base, cancelled: true })).toBe("cancelled");
    expect(shouldStopReconnect({ ...base, terminal: "completed" })).toBe(
      "terminal",
    );
    expect(shouldStopReconnect({ ...base, signedOut: true })).toBe("signed_out");
    expect(shouldStopReconnect({ ...base, unauthorized: true })).toBe(
      "signed_out",
    );
    expect(shouldStopReconnect({ ...base, runDeleted: true })).toBe(
      "run_deleted",
    );
    expect(shouldStopReconnect({ ...base, unmounted: true })).toBe("unmounted");
    expect(shouldStopReconnect({ ...base, attemptIndex: 3 })).toBe("exhausted");
  });

  it("waits the delay and aborts when the signal fires", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const pending = waitForReconnectDelay(500, controller.signal);
    await vi.advanceTimersByTimeAsync(499);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
