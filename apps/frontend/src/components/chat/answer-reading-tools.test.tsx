// @vitest-environment jsdom

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { createChatViewState } from "../../lib/chat-view";
import { AnswerSurface } from "./answer-surface";
import { CitationSheet } from "./citation-sheet";
import { CopyAnswerButton } from "./copy-answer-button";
import { AnswerFigure, figureTextParts } from "./answer-figure";

vi.mock("../../lib/auth/session-provider", () => ({
  useOptionalSession: () => ({ accessToken: "inert-test-token" }),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Answer reading tools", () => {
  it("shows loading and recoverable errors without claiming sources are empty", () => {
    const retry = vi.fn();
    const props = {
      open: true,
      onClose: vi.fn(),
      citations: [],
      hrefForCitation: () => undefined,
      onSelectCitation: vi.fn(),
    };
    const { rerender } = render(<CitationSheet {...props} pending />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading sources");
    expect(screen.queryByText("No citations for this run yet.")).toBeNull();
    rerender(<CitationSheet {...props} error onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Sources could not be loaded",
    );
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("copies the original code and prose without leaking internal figure markers", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    render(
      <CopyAnswerButton
        text={
          "Use &lt;value&gt;.\n\n```python\ndef f():\n    return 1\n```\n[[figure:abc123]]"
        }
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Copied"),
    );
    expect(writeText).toHaveBeenCalledWith(
      "Use <value>.\n\n```python\ndef f():\n    return 1\n```",
    );
  });

  it("reports clipboard denial without a false success", async () => {
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
    render(<CopyAnswerButton text="Answer" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy answer" }));
    expect(await screen.findByText("Copy failed")).toBeInTheDocument();
  });

  it("keeps run-owned inline citations after the live answer enters history", () => {
    const chat = {
      ...createChatViewState("test"),
      runId: "run-a",
      terminal: "completed" as const,
    };
    const props = {
      question: "",
      answer: "Verified answer.",
      terminal: "completed",
      chat,
      answerOrigin: "company_documents",
      hrefForCitation: () => undefined,
      onSelectCitation: vi.fn(),
      citations: [
        {
          citation_id: "c-a",
          citation_index: 1,
          chunk_id: "chunk",
          paragraph_index: 0,
          provenance: {},
          source_unavailable: false,
        },
      ],
    };
    const message = {
      message_id: "m-a",
      role: "assistant" as const,
      content: "Verified answer.",
      created_at: "2026-10-21T00:00:00Z",
      run_id: "run-a",
      citation_count: 1,
    };
    const { rerender } = render(
      <AnswerSurface {...props} messages={[message]} />,
    );
    expect(screen.getByTestId("answer-source-list")).toBeInTheDocument();
    rerender(
      <AnswerSurface
        {...props}
        answer=""
        messages={[{ ...message, run_id: "foreign-run" }]}
      />,
    );
    expect(screen.queryByTestId("answer-source-list")).toBeNull();
  });

  it("separates the printed figure caption without changing the source wording", () => {
    expect(
      figureTextParts(
        "Introduction.\nFigure 5-1. Query handling\nThe diagram shows a query.",
      ),
    ).toEqual({
      introduction: "Introduction.",
      caption: "Figure 5-1. Query handling",
      description: "The diagram shows a query.",
    });
    expect(figureTextParts("شرح الرسم بالعربية").caption).toBe(
      "شرح الرسم بالعربية",
    );
  });

  it("enlarges an authorized image and releases its URL on unmount", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: true,
          blob: async () => new Blob(["png"], { type: "image/png" }),
        }),
    );
    const create = vi.fn(() => "blob:authorized-figure");
    const revoke = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: revoke });
    const { unmount } = render(
      <AnswerFigure
        figureId="abc123"
        caption="Figure 5-1. Query handling\nSource description."
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Enlarge diagram" }),
    );
    const dialog = screen.getByRole("dialog", { name: "Diagram" });
    expect(within(dialog).getByRole("img")).toHaveAttribute(
      "src",
      "blob:authorized-figure",
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Enlarge diagram" })).toHaveFocus();
    unmount();
    expect(revoke).toHaveBeenCalledWith("blob:authorized-figure");
  });

  it("keeps the caption when image access is denied", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    render(
      <AnswerFigure figureId="abc123" caption="Figure 5-1. Query handling" />,
    );
    expect(
      await screen.findByText("Diagram preview is unavailable."),
    ).toBeInTheDocument();
    expect(screen.getByText("Figure 5-1. Query handling")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Enlarge diagram" }),
    ).toBeNull();
  });
});
