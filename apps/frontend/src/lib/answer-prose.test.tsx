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

  it("renders ordered lists", () => {
    const { container } = render(
      <>
        {renderAnswerProse("1. One\n2. Two", "prose", "list", "inline")}
      </>,
    );
    expect(container.querySelectorAll("ol.list li")).toHaveLength(2);
  });
});
