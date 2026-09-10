import { describe, expect, it } from "vitest";
import {
  citationCompareAllowed,
  evalAiRequestBody,
  holdoutCannotRun,
  pdfEvalCapability,
} from "./eval-workspace";

describe("eval workspace helpers", () => {
  it("hides the tab unless meta capability is true", () => {
    expect(pdfEvalCapability(null)).toBe(false);
    expect(pdfEvalCapability({ pdf_eval_workspace: false })).toBe(false);
    expect(pdfEvalCapability({ pdf_eval_workspace: true })).toBe(true);
  });

  it("sends only the question to the paid Ask body", () => {
    expect(evalAiRequestBody("What is Hybrid?")).toEqual({
      message: "What is Hybrid?",
    });
    expect(evalAiRequestBody("What is Hybrid?")).not.toHaveProperty(
      "expected_answer",
    );
  });

  it("forbids citation compare before completed and holdout runs", () => {
    expect(citationCompareAllowed(null)).toBe(false);
    expect(citationCompareAllowed("error")).toBe(false);
    expect(citationCompareAllowed("completed")).toBe(true);
    expect(holdoutCannotRun("development")).toBe(false);
    expect(holdoutCannotRun("holdout")).toBe(true);
  });
});
