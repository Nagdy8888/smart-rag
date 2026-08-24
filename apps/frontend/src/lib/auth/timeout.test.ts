import { describe, expect, it, vi } from "vitest";
import { raceTimeout } from "./timeout";

describe("raceTimeout", () => {
  it("resolves when the work finishes first", async () => {
    await expect(raceTimeout(Promise.resolve("ok"), 50, "late")).resolves.toBe(
      "ok",
    );
  });

  it("rejects with the label when the timer fires first", async () => {
    vi.useFakeTimers();
    const pending = raceTimeout(new Promise<string>(() => {}), 20, "late");
    const expectation = expect(pending).rejects.toThrow("late");
    await vi.advanceTimersByTimeAsync(20);
    await expectation;
    vi.useRealTimers();
  });
});
