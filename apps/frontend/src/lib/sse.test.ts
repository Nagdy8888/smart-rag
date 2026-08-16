import { describe, expect, it } from "vitest";
import { parseSseBuffer, parseSsePayload, isKnownSseEvent } from "./sse";

describe("parseSseBuffer", () => {
  it("parses catalog frames and leaves a partial tail", () => {
    const { frames, rest } = parseSseBuffer(
      "event: status\nid: 1\ndata: {\"stage\":\"retrieve\",\"status\":\"running\"}\n\nevent: token_delta\ndata: {\"delta\":\"Hi\"}\n\nevent: par",
    );
    expect(frames).toHaveLength(2);
    expect(frames[0]?.event).toBe("status");
    expect(frames[0]?.id).toBe("1");
    expect(frames[1]?.event).toBe("token_delta");
    expect(rest.startsWith("event: par")).toBe(true);
  });
});

describe("parseSsePayload", () => {
  it("returns empty object for non-object JSON", () => {
    expect(parseSsePayload("[1]")).toEqual({});
    expect(parseSsePayload("not-json")).toEqual({});
  });
});

describe("isKnownSseEvent", () => {
  it("rejects unknown additive types so callers can ignore them", () => {
    expect(isKnownSseEvent("status")).toBe(true);
    expect(isKnownSseEvent("future_metric")).toBe(false);
  });
});
