import { describe, expect, it } from "vitest";
import {
  CONVERSATION_TITLE_MAX,
  conversationTitleFromPrompt,
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
