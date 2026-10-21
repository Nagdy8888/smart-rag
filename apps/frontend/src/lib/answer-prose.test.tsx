// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { renderAnswerProse } from "./answer-prose";

describe("answer prose markdown-lite", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders bold, inline code, and a bullet list", () => {
    const { container } = render(
      <>
        {renderAnswerProse(
          ["Use **bold** and `code`.", "", "- First", "- Second"].join("\n"),
          "prose",
          "list",
          "inline",
        )}
      </>,
    );
    expect(screen.getByTestId("answer-prose")).toBeInTheDocument();
    expect(container.querySelector("strong")).toHaveTextContent("bold");
    expect(container.querySelector("code.inline")).toHaveTextContent("code");
    expect(container.querySelectorAll("ul.list li")).toHaveLength(2);
  });

  it("keeps hostile markup as text", () => {
    const { container } = render(
      <>
        {renderAnswerProse(
          "See **safe** and <img src=x onerror=alert(1)>",
          "prose",
          "list",
          "inline",
        )}
      </>,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByTestId("answer-prose").textContent).toContain(
      "<img src=x onerror=alert(1)>",
    );
  });

  it("makes http links clickable and leaves other schemes as text", () => {
    const { container } = render(
      <>
        {renderAnswerProse(
          "Read https://example.com/docs. and [the notes](https://example.com/notes) then [bad](javascript:alert(1)).",
          "prose",
          "list",
          "inline",
        )}
      </>,
    );
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "https://example.com/docs");
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
    expect(links[1]).toHaveAttribute("href", "https://example.com/notes");
    expect(links[1]).toHaveTextContent("the notes");
    expect(container.querySelector("a[href^='javascript:']")).toBeNull();
    expect(screen.getByTestId("answer-prose").textContent).toContain(
      "javascript:alert(1)",
    );
  });

  it("keeps a URL inside inline code as text", () => {
    const { container } = render(
      <>
        {renderAnswerProse(
          "Run `https://example.com/hook` locally.",
          "prose",
          "list",
          "inline",
        )}
      </>,
    );
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("code")).toHaveTextContent(
      "https://example.com/hook",
    );
  });

  it("renders a bold title above an ordered list and leaves a sentence as prose", () => {
    const { container } = render(
      <>
        {renderAnswerProse(
          ["**Setup**", "1. One", "2. Two"].join("\n"),
          "prose",
          "list",
          "inline",
          "heading",
        )}
      </>,
    );
    const heading = screen.getByRole("heading", { level: 3, name: "Setup" });
    expect(heading).toHaveClass("heading");
    expect(container.querySelectorAll("ol.list li")).toHaveLength(2);
  });

  it("keeps connected sentences together as readable prose", () => {
    const { container } = render(
      <>
        {renderAnswerProse(
          "The window is 30 days. The request must be in writing.",
          "prose",
          "list",
          "inline",
          "heading",
        )}
      </>,
    );
    expect(container.querySelector("ol")).toBeNull();
    expect(container.querySelectorAll("p.prose")).toHaveLength(1);
    expect(container.querySelector("p.prose")).toHaveTextContent(
      "The window is 30 days. The request must be in writing.",
    );
  });

  it("preserves a multi-sentence paragraph under its heading", () => {
    const { container } = render(
      <>
        {renderAnswerProse(
          ["**Setup**", "The window is 30 days. The request must be in writing."].join(
            "\n",
          ),
          "prose",
          "list",
          "inline",
          "heading",
        )}
      </>,
    );
    expect(screen.getByRole("heading", { level: 3, name: "Setup" })).toBeInTheDocument();
    expect(container.querySelector("ol")).toBeNull();
    expect(container.querySelectorAll("p.prose")).toHaveLength(1);
    expect(screen.getByText("The window is 30 days. The request must be in writing.")).toBeInTheDocument();
  });

  it("leaves a one-sentence paragraph as text", () => {
    const { container } = render(
      <>
        {renderAnswerProse("The refund period is 30 days.", "prose", "list", "inline")}
      </>,
    );
    expect(container.querySelector("h3")).toBeNull();
    expect(container.querySelector("ol")).toBeNull();
    expect(screen.getByText("The refund period is 30 days.")).toBeInTheDocument();
  });

  it("renders a markdown heading and leaves a one-sentence paragraph as text", () => {
    render(
      <>
        {renderAnswerProse("## Memory\nEdges run in order.", "prose", "list", "inline", "heading")}
      </>,
    );
    expect(screen.getByRole("heading", { level: 3, name: "Memory" })).toBeInTheDocument();
    expect(screen.getByText("Edges run in order.")).toBeInTheDocument();
  });

  it("renders ordered lists", () => {
    const { container } = render(
      <>
        {renderAnswerProse("1. One\n2. Two", "prose", "list", "inline")}
      </>,
    );
    expect(container.querySelectorAll("ol.list li")).toHaveLength(2);
  });

  it("keeps a long explanation organized by authored headings and paragraphs", () => {
    const explanation = [
      "## Understanding the request",
      "The agent identifies the goal. It uses context to resolve ambiguity.",
      "",
      "It asks for clarification when the missing information affects the result.",
      "",
      "**Choosing tools**",
      "The agent selects a tool. It checks the result before continuing.",
      "",
      "- Check the inputs",
      "- Confirm the outcome",
    ].join("\n");
    const { container } = render(
      <>{renderAnswerProse(explanation, "prose", "list", "inline", "heading")}</>,
    );
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(2);
    expect(container.querySelectorAll("p.prose")).toHaveLength(3);
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(container.querySelector("ol")).toBeNull();
    expect(screen.getByText("The agent identifies the goal. It uses context to resolve ambiguity.")).toBeInTheDocument();
  });
});
