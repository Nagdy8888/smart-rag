import { describe, expect, it } from "vitest";
import { formatCodeSnippet, isCodeSnippet } from "./code-snippet";

describe("code snippets", () => {
  it("turns a flattened function into separate lines", () => {
    const flat =
      '@tool def multiply(x: float, y: float) -> float: """Multiply \'x\' times \'y\'.""" return x * y';
    expect(isCodeSnippet(flat)).toBe(true);
    expect(formatCodeSnippet(flat)).toBe(
      [
        "@tool",
        "def multiply(x: float, y: float) -> float:",
        '    """Multiply \'x\' times \'y\'."""',
        "    return x * y",
      ].join("\n"),
    );
  });

  it("leaves ordinary prose alone", () => {
    expect(isCodeSnippet("The refund period is 30 days.")).toBe(false);
  });

  it("puts a curly-quote docstring on its own line", () => {
    const mixed =
      "The multiply tool is defined by the function @tool def multiply(x: float, y: float) → float: \u201c\u201c\u201cMultiply 'x' times 'y'.\u201d\u201d\u201d return x * y.";
    expect(formatCodeSnippet(mixed)).toBe(
      [
        "@tool",
        "def multiply(x: float, y: float) → float:",
        "    \u201c\u201c\u201cMultiply 'x' times 'y'.\u201d\u201d\u201d",
        "    return x * y",
      ].join("\n"),
    );
  });

  it("drops the sentence around a function", () => {
    const mixed =
      "The multiply tool in the Chapter 4 local calculator example is defined by the function `@tool def multiply(x: float, y: float) -> float: \"\"\"Multiply 'x' times 'y'.\"\"\" return x * y.";
    expect(formatCodeSnippet(mixed)).toBe(
      [
        "@tool",
        "def multiply(x: float, y: float) -> float:",
        '    """Multiply \'x\' times \'y\'."""',
        "    return x * y",
      ].join("\n"),
    );
  });
});
