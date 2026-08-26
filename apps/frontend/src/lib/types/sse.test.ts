import { describe, expect, it } from "vitest";

import { KNOWN_SSE_EVENT_TYPES, TERMINAL_SSE_EVENT_TYPES } from "./sse";

describe("SSE catalog names", () => {
  it("lists the known persisted event types", () => {
    expect([...KNOWN_SSE_EVENT_TYPES]).toEqual([
      "schema",
      "status",
      "tool_progress",
      "heartbeat",
      "route_correction",
      "limitation",
      "deadline",
      "partial",
      "cache",
      "coverage",
      "optional_tool_disclosure",
      "citation_preview",
      "answer_origin",
      "token_delta",
      "usage",
      "completed",
      "cancelled",
      "error",
    ]);
  });

  it("keeps catalog terminals first-terminal-wins", () => {
    expect([...TERMINAL_SSE_EVENT_TYPES]).toEqual([
      "completed",
      "cancelled",
      "error",
      "partial",
    ]);
    const diagnostic = "deadline";
    expect((TERMINAL_SSE_EVENT_TYPES as readonly string[]).includes(diagnostic)).toBe(
      false,
    );
  });
});
