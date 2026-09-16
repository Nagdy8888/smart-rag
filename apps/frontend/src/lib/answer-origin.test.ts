import { describe, expect, it } from "vitest";
import {
  MIXED_SCOPE_CLARIFICATION,
  answerOriginLabel,
  answerOriginTone,
  isAnswerOrigin,
  shouldShowCitations,
} from "./answer-origin";

describe("answer origin helpers", () => {
  it("maps each catalog origin to its label and tone", () => {
    expect(answerOriginLabel("general_knowledge")).toBe("General knowledge");
    expect(answerOriginLabel("company_documents")).toBe("Company documents");
    expect(answerOriginLabel("user_supplied_text")).toBe("Your text");
    expect(answerOriginLabel("deterministic")).toBe("Assistant");
    expect(answerOriginLabel("ambiguous")).toBe("Needs clarification");
    expect(answerOriginLabel("web")).toBe("Web");
    expect(answerOriginTone("company_documents")).toBe("success");
    expect(answerOriginTone("web")).toBe("success");
    expect(answerOriginTone("ambiguous")).toBe("warning");
    expect(answerOriginTone("general_knowledge")).toBe("neutral");
  });

  it("shows citations for company, web, or a missing origin", () => {
    expect(shouldShowCitations("company_documents")).toBe(true);
    expect(shouldShowCitations("web")).toBe(true);
    expect(shouldShowCitations(null)).toBe(true);
    expect(shouldShowCitations("general_knowledge")).toBe(false);
    expect(shouldShowCitations("user_supplied_text")).toBe(false);
    expect(shouldShowCitations("deterministic")).toBe(false);
    expect(shouldShowCitations("ambiguous")).toBe(false);
    expect(shouldShowCitations("not_a_catalog_origin")).toBe(false);
  });

  it("isolates unknown origin text and never treats it as HTML", () => {
    expect(isAnswerOrigin("<script>x</script>")).toBe(false);
    expect(answerOriginLabel("<script>x</script>")).toBe("<script>x</script>");
    expect(answerOriginTone("<script>x</script>")).toBe("neutral");
  });

  it("keeps the mixed-scope clarification copy stable", () => {
    expect(MIXED_SCOPE_CLARIFICATION).toBe(
      "This question mixes general knowledge and company documents. Ask one general question or one document question so the answer source stays clear.",
    );
  });
});
