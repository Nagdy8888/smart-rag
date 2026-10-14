/**
 * Browser error scrubbing before a GlitchTip send.
 */

import { describe, expect, it } from "vitest";
import { scrubBrowserErrorEvent } from "./browser-error-telemetry";

describe("scrubBrowserErrorEvent", () => {
  it("drops request bodies and redacts bearer tokens", () => {
    const event = scrubBrowserErrorEvent({
      message: "failed Bearer abc.def token",
      request: {
        cookies: { session: "secret" },
        headers: { Authorization: "Bearer abc.def" },
        data: { passage: "source text" },
      },
      extra: { passage: "source text", event: "ui.failed" },
      exception: {
        values: [{ value: "sk-abcdefghijklmnopqrstuvwxyz" }],
      },
    });

    expect(event.request?.cookies).toBeUndefined();
    expect(event.request?.headers).toBeUndefined();
    expect(event.request?.data).toBeUndefined();
    expect(event.extra).toEqual({ event: "ui.failed" });
    expect(event.message).toContain("Bearer [REDACTED]");
    expect(event.exception?.values?.[0]?.value).toBe("[REDACTED]");
  });
});
