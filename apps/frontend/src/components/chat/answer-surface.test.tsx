// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { MIXED_SCOPE_CLARIFICATION } from "../../lib/answer-origin";
import type { CitationResponse } from "../../lib/types";
import { AnswerSurface } from "./answer-surface";

const CITATION: CitationResponse = {
  citation_id: "cite-1",
  citation_index: 1,
  chunk_id: "chunk-1",
  provenance: {},
  source_unavailable: false,
};

function renderSurface(
  overrides: Partial<Parameters<typeof AnswerSurface>[0]> = {},
) {
  return render(
    <AnswerSurface
      question="What is our refund policy?"
      answer="The refund period is 30 days."
      citations={[CITATION]}
      terminal="completed"
      hrefForCitation={() => undefined}
      onSelectCitation={vi.fn()}
      {...overrides}
    />,
  );
}

describe("AnswerSurface origin chrome", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders each catalog origin label without inferring from the route", () => {
    const labels = [
      ["general_knowledge", "General knowledge"],
      ["company_documents", "Company documents"],
      ["user_supplied_text", "Your text"],
      ["deterministic", "Assistant"],
      ["ambiguous", "Needs clarification"],
    ] as const;
    for (const [origin, label] of labels) {
      const { unmount } = renderSurface({
        answerOrigin: origin,
        effectiveRoute: "hybrid",
      });
      expect(screen.getByTestId("answer-origin")).toHaveTextContent(label);
      expect(screen.getByTestId("answer-route")).toHaveTextContent("hybrid");
      unmount();
    }
  });

  it("hides citations for general, user-text, and deterministic origins", () => {
    for (const origin of ["general_knowledge", "user_supplied_text", "deterministic"] as const) {
      const { unmount } = renderSurface({ answerOrigin: origin });
      expect(screen.queryByTestId("answer-citations")).not.toBeInTheDocument();
      unmount();
    }
  });

  it("shows citations for company origin and for a null legacy origin", () => {
    const { rerender } = renderSurface({ answerOrigin: "company_documents" });
    expect(screen.getByTestId("answer-citations")).toBeInTheDocument();
    rerender(
      <AnswerSurface
        question="q"
        answer="a"
        citations={[CITATION]}
        terminal="completed"
        hrefForCitation={() => undefined}
        onSelectCitation={vi.fn()}
        answerOrigin={null}
      />,
    );
    expect(screen.getByTestId("answer-citations")).toBeInTheDocument();
  });

  it("shows clarification and no citation chips for an ambiguous origin", () => {
    renderSurface({ answerOrigin: "ambiguous" });
    expect(screen.getByText(MIXED_SCOPE_CLARIFICATION)).toBeInTheDocument();
    expect(screen.queryByTestId("answer-citations")).not.toBeInTheDocument();
  });

  it("tolerates an unknown origin and never renders it as HTML", () => {
    const { container } = renderSurface({
      answerOrigin: "<img src=x onerror=alert(1)>",
    });
    expect(screen.getByTestId("answer-origin")).toHaveTextContent(
      "<img src=x onerror=alert(1)>",
    );
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows this run's prompt and completion tokens", () => {
    renderSurface({ promptTokens: 1234, completionTokens: 88 });
    expect(screen.getByTestId("answer-token-usage")).toHaveTextContent(
      "1,234 prompt · 88 completion",
    );
  });

  it("hides the token line when the run spent none", () => {
    renderSurface({ promptTokens: 0, completionTokens: 0 });
    expect(screen.queryByTestId("answer-token-usage")).not.toBeInTheDocument();
  });

  it("does not render assistant prose before verified tokens exist", () => {
    render(
      <AnswerSurface
        question="What is our refund policy?"
        answer=""
        citations={[]}
        terminal={null}
        progressItems={[
          {
            id: "n:generate_answer",
            kind: "node",
            key: "generate_answer",
            phase: "started",
            outcome: null,
            firstSequence: 1,
            lastSequence: 1,
          },
        ]}
        verificationCompleted={false}
        hrefForCitation={() => undefined}
        onSelectCitation={vi.fn()}
      />,
    );
    expect(screen.getAllByText("Generating…").length).toBeGreaterThan(0);
    expect(screen.queryByText("The refund period is 30 days.")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verified-answer-reveal")).not.toBeInTheDocument();
  });

  it("does not treat a pending transcript as a new chat", () => {
    render(
      <AnswerSurface
        messagesPending
        question=""
        answer=""
        citations={[]}
        terminal={null}
        hrefForCitation={() => undefined}
        onSelectCitation={vi.fn()}
      />,
    );
    expect(screen.getByText("Loading conversation…")).toBeInTheDocument();
    expect(
      screen.queryByText("Ask your company knowledge"),
    ).not.toBeInTheDocument();
  });

  it("renders API-escaped quotes as quotation marks", () => {
    renderSurface({
      messages: [
        {
          message_id: "m1",
          role: "assistant",
          content:
            "&quot;Hello from the other side&quot; is a popular lyric",
          created_at: "2026-08-17T00:00:00Z",
        },
      ],
      question: "",
      answer: "",
      terminal: null,
    });
    expect(
      screen.getByText('"Hello from the other side" is a popular lyric'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/&quot;/)).not.toBeInTheDocument();
  });

  it("uses the dual-mode empty state", () => {
    render(
      <AnswerSurface
        question=""
        answer=""
        citations={[]}
        terminal={null}
        hrefForCitation={() => undefined}
        onSelectCitation={vi.fn()}
      />,
    );
    expect(
      screen.getByText(
        "Ask your company knowledge",
      ),
    ).toBeInTheDocument();
  });
});
