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

  it("renders ordered lists", () => {
    const { container } = render(
      <>
        {renderAnswerProse("1. One\n2. Two", "prose", "list", "inline")}
      </>,
    );
    expect(container.querySelectorAll("ol.list li")).toHaveLength(2);
  });
});
