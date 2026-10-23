// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { AnswerCodeBlock } from "./answer-code-block";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("IDE-style code", () => {
  it.each([
    ["python", 'def greet(name):\n    # Greeting\n    return "Hello " + name'],
    ["javascript", 'const value = "<img src=x onerror=alert(1)>";'],
    ["json", '{"enabled": true, "count": 42}'],
    ["sql", "SELECT name FROM users WHERE id = 42;"],
  ])("colors %s tokens while preserving exact source", (language, code) => {
    const { container } = render(<AnswerCodeBlock language={language} code={code} />);
    expect(container.querySelector("code")?.textContent).toBe(code);
    expect(container.querySelector("code span[class*='hljs-']")).not.toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("copies the exact displayed code, including literal HTML entities", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const code = 'const entity = "&amp;";';
    const { container } = render(<AnswerCodeBlock language="javascript" code={code} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy javascript snippet" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(code));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("javascript snippet copied."));
    expect(container.querySelector("code")).toHaveAttribute("translate", "no");
    expect(container.querySelector("code")?.textContent).toBe(code);
  });

  it("announces a useful recovery when clipboard permission is denied", async () => {
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
    render(<AnswerCodeBlock language="python" code="print(1)" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy python snippet" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Copy failed. Select the code and copy it manually."));
    expect(screen.getByRole("button", { name: "Copy python snippet" })).toBeEnabled();
  });

  it("retains unknown languages and oversized snippets as readable plain text", () => {
    const code = "<script>unsafe()</script>";
    const { container, rerender } = render(<AnswerCodeBlock language="unknown" code={code} />);
    expect(container.querySelector("code")?.textContent).toBe(code);
    expect(container.querySelector("script")).toBeNull();
    const large = "x".repeat(33_000);
    rerender(<AnswerCodeBlock language="python" code={large} />);
    expect(container.querySelector("code")?.textContent).toBe(large);
  });
});
