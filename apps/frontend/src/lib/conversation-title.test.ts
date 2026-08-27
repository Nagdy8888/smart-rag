import { describe, expect, it } from "vitest";
import {
  CONVERSATION_TITLE_MAX,
  conversationTitleFromPrompt,
  conversationTitleNeedsLlm,
} from "./conversation-title";

describe("conversationTitleFromPrompt", () => {
  it("returns Chat for blank input", () => {
    expect(conversationTitleFromPrompt("")).toBe("Chat");
    expect(conversationTitleFromPrompt("   \n\t")).toBe("Chat");
  });

  it("collapses whitespace into one line", () => {
    expect(conversationTitleFromPrompt("  Summarize\nthe policy  ")).toBe(
      "Summarize the policy",
    );
  });

  it("truncates long prompts at the documented bound", () => {
    const long = "A".repeat(CONVERSATION_TITLE_MAX + 12);
    const title = conversationTitleFromPrompt(long);
    expect(title.endsWith("…")).toBe(true);
    expect(title.length).toBe(CONVERSATION_TITLE_MAX);
  });
});

describe("conversationTitleNeedsLlm", () => {
  it("treats missing and first-prompt titles as fallbacks", () => {
    expect(conversationTitleNeedsLlm(null, "Summarize the policy")).toBe(true);
    expect(conversationTitleNeedsLlm("Chat", "Summarize the policy")).toBe(true);
    expect(
      conversationTitleNeedsLlm("Summarize the policy", "Summarize the policy"),
    ).toBe(true);
  });

  it("skips titles that already describe the thread", () => {
    expect(
      conversationTitleNeedsLlm("Vacation policy", "Summarize the policy"),
    ).toBe(false);
  });
});
