import { describe, expect, it } from "vitest";
import {
  formatCodeSnippet,
  formatCodeSnippetModel,
  isCodeSnippet,
  splitTrailingSourceListing,
} from "./code-snippet";

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

  it("preserves multiline salvage bodies without flattening", () => {
    const multi = [
      "@tool",
      "def cancel_order(order_id: str) -> str:",
      '    """Cancel an order that hasn\'t shipped."""',
      '    return f"Order {order_id} has been cancelled."',
    ].join("\n");
    expect(isCodeSnippet(multi)).toBe(true);
    expect(formatCodeSnippet(multi)).toBe(multi);
  });

  it("reformats sparse-newline compacted defs that share a line with return", () => {
    const sparse = [
      '@tool def cancel_order(order_id: str) -> str: """Cancel an order that hasn\'t shipped.""" # note return f"Order {order_id} has been cancelled."',
      "# -- trailing commentary from a wider excerpt",
    ].join("\n");
    expect(formatCodeSnippet(sparse)).toBe(
      [
        "@tool",
        "def cancel_order(order_id: str) -> str:",
        '    """Cancel an order that hasn\'t shipped.""" # note',
        '    return f"Order {order_id} has been cancelled."',
      ].join("\n"),
    );
  });

  it("drops a sibling def that trails after the primary return", () => {
    const flat =
      '@tool def cancel_order(order_id: str) -> str: """Cancel.""" return f"Order {order_id} has been cancelled." def call_model(state): return state';
    expect(formatCodeSnippet(flat)).toBe(
      [
        "@tool",
        "def cancel_order(order_id: str) -> str:",
        '    """Cancel."""',
        '    return f"Order {order_id} has been cancelled."',
      ].join("\n"),
    );
  });

  it("detects a bare @tool paragraph", () => {
    expect(isCodeSnippet("@tool\nprint('ready')")).toBe(true);
  });

  it("leaves ordinary prose alone", () => {
    expect(isCodeSnippet("The refund period is 30 days.")).toBe(false);
    expect(splitTrailingSourceListing("The refund period is 30 days.")).toBeNull();
    expect(splitTrailingSourceListing("from the handbook we copy the steps.")).toBeNull();
  });

  it("splits a trailing import listing and keeps a wrapped import tail", () => {
    const split = splitTrailingSourceListing(
      [
        "Load the helpers before calling them.",
        "from pkg.mod import Widget",
        "12",
        "from pkg.other import Helper,",
        "ExtraName",
        "from lan",
      ].join("\n"),
    );
    expect(split?.prose).toBe("Load the helpers before calling them.");
    expect(split?.language).toBe("python");
    expect(split?.code).toBe(
      [
        "from pkg.mod import Widget",
        "from pkg.other import Helper,",
        "ExtraName",
        "from lan",
      ].join("\n"),
    );
  });

  it("detects a fenced python block and strips fences", () => {
    const fenced = ["```python", "def hello():", "    return 1", "```"].join("\n");
    expect(isCodeSnippet(fenced)).toBe(true);
    expect(formatCodeSnippetModel(fenced)).toEqual({
      language: "python",
      code: "def hello():\n    return 1",
    });
  });

  it("keeps a fence with a blank line before the closer", () => {
    const fenced = [
      "```python",
      "def hello():",
      "    return 1",
      "",
      "```",
    ].join("\n");
    expect(formatCodeSnippetModel(fenced)).toEqual({
      language: "python",
      code: "def hello():\n    return 1",
    });
  });

  it("detects a fenced js block without a language on the whole paragraph", () => {
    const fenced = ["```js", "const x = 1;", "```"].join("\n");
    expect(formatCodeSnippetModel(fenced)).toEqual({
      language: "js",
      code: "const x = 1;",
    });
  });

  it("labels salvaged @tool defs as python", () => {
    const flat =
      '@tool def multiply(x: float, y: float) -> float: """Multiply.""" return x * y';
    expect(formatCodeSnippetModel(flat).language).toBe("python");
  });

  it("splits a signature that uses a non-ascii arrow", () => {
    const mixed =
      "defined by @tool def multiply(x: float, y: float) \u2794 float: \"\"\"Multiply 'x' times 'y'.\"\"\" return x * y";
    expect(formatCodeSnippet(mixed)).toBe(
      [
        "@tool",
        "def multiply(x: float, y: float) \u2794 float:",
        '    """Multiply \'x\' times \'y\'."""',
        "    return x * y",
      ].join("\n"),
    );
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
