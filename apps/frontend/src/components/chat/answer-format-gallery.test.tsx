/**
 * Empty-state format gallery renders live answer chrome for canned samples.
 */

// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { AnswerFormatGallery } from "./answer-format-gallery";

afterEach(() => {
  cleanup();
});

describe("AnswerFormatGallery", () => {
  it("shows a code block for the default Code sample", () => {
    render(<AnswerFormatGallery />);
    expect(screen.getByTestId("answer-format-gallery")).toBeInTheDocument();
    expect(screen.getByTestId("answer-format-preview")).toHaveAttribute(
      "data-sample",
      "code",
    );
    expect(screen.getByText(/cancel_order/)).toBeInTheDocument();
    expect(document.querySelector("pre code")).not.toBeNull();
  });

  it("switches to an HTML table for the Table sample", async () => {
    const user = userEvent.setup();
    render(<AnswerFormatGallery />);
    await user.click(screen.getByRole("tab", { name: "Table" }));
    expect(screen.getByTestId("answer-format-preview")).toHaveAttribute(
      "data-sample",
      "table",
    );
    const table = document.querySelector("table");
    expect(table).not.toBeNull();
    expect(table?.querySelectorAll("th").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("Gemma 2")).toBeInTheDocument();
  });

  it("renders the RACI sample as a table with Hallucination rates", async () => {
    const user = userEvent.setup();
    render(<AnswerFormatGallery />);
    await user.click(screen.getByRole("tab", { name: "RACI" }));
    expect(screen.getByText("Hallucination rates")).toBeInTheDocument();
    expect(document.querySelector("table")).not.toBeNull();
    expect(screen.queryByText(/^call delays\)$/i)).toBeNull();
  });

  it("renders bold and lists for the Prose sample", async () => {
    const user = userEvent.setup();
    render(<AnswerFormatGallery />);
    await user.click(screen.getByRole("tab", { name: "Prose" }));
    expect(document.querySelector("strong")).not.toBeNull();
    expect(document.querySelector("ul")).not.toBeNull();
    expect(document.querySelector("ol")).not.toBeNull();
    expect(screen.queryByText(/\*\*refund window\*\*/)).toBeNull();
  });
});
