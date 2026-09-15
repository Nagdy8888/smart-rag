// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { MIXED_SCOPE_CLARIFICATION } from "../../lib/answer-origin";
import { EMPTY_DEADLINE_PARTIAL_COPY } from "../../lib/run-details";
import type { CitationResponse } from "../../lib/types";
import { AnswerSurface, answerTerminalNote, transcriptTextMatches } from "./answer-surface";

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
      expect(screen.getByTestId("answer-route")).toHaveTextContent("Hybrid");
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

  it("labels company citations with typed title and PDF page", () => {
    renderSurface({
      answerOrigin: "company_documents",
      citations: [
        {
          citation_id: "cite-1",
          citation_index: 0,
          chunk_id: "chunk-1",
          provenance: { page_number: 12, page_label: "12", document_title: "AI agents" },
          source_unavailable: false,
          document_title: "AI agents",
          pdf_page_number: 129,
          paragraph_index: 0,
        },
      ],
    });
    expect(
      screen.getByRole("button", { name: "Citation 0, AI agents · PDF page 129" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("cite-1")).not.toBeInTheDocument();
    expect(screen.queryByText("p. 12")).not.toBeInTheDocument();
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

  it("does not treat a failed transcript as a new chat", () => {
    render(
      <AnswerSurface
        messagesError
        question=""
        answer=""
        citations={[]}
        terminal={null}
        hrefForCitation={() => undefined}
        onSelectCitation={vi.fn()}
      />,
    );
    expect(
      screen.getByText("Couldn't load this conversation."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Ask a general question, or ask about your company documents for a cited answer.",
      ),
    ).not.toBeInTheDocument();
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
      screen.queryByText(
        "Ask a general question, or ask about your company documents for a cited answer.",
      ),
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

  it("does not render the live assistant twice after an escaped transcript refetch", () => {
    const answer =
      "Company documents were not searched because the question's scope could not be established.";
    renderSurface({
      messages: [
        {
          message_id: "u1",
          role: "user",
          content: "Find a relationship between entities.",
          created_at: "2026-08-27T11:08:00Z",
        },
        {
          message_id: "a1",
          role: "assistant",
          content:
            "Company documents were not searched because the question&#x27;s scope could not be established.",
          created_at: "2026-08-27T11:08:20Z",
        },
      ],
      question: "Find a relationship between entities.",
      answer,
      terminal: "completed",
      answerOrigin: "general_knowledge",
      effectiveRoute: "composite",
      verificationCompleted: true,
      progressItems: [
        {
          id: "n:verify_answer",
          kind: "node",
          key: "verify_answer",
          phase: "completed",
          outcome: "verified",
          firstSequence: 3,
          lastSequence: 3,
        },
      ],
    });
    expect(screen.getAllByText(answer)).toHaveLength(1);
    expect(screen.queryByTestId("verified-answer-reveal")).not.toBeInTheDocument();
    expect(screen.queryByTestId("answer-route")).not.toBeInTheDocument();
  });

  it("does not duplicate the user bubble when the persisted question is escaped", () => {
    renderSurface({
      messages: [
        {
          message_id: "u1",
          role: "user",
          content: "What&#x27;s our refund policy?",
          created_at: "2026-08-27T11:08:00Z",
        },
      ],
      question: "What's our refund policy?",
      answer: "",
      terminal: null,
      citations: [],
    });
    expect(screen.getAllByText("What's our refund policy?")).toHaveLength(1);
  });

  it("keeps the live assistant when the last persisted answer is a prior turn", () => {
    renderSurface({
      messages: [
        {
          message_id: "a-old",
          role: "assistant",
          content: "Previous verified answer.",
          created_at: "2026-08-27T11:00:00Z",
        },
      ],
      question: "Follow up",
      answer: "New verified answer.",
      terminal: "completed",
      effectiveRoute: "composite",
    });
    expect(screen.getByText("Previous verified answer.")).toBeInTheDocument();
    expect(screen.getByText("New verified answer.")).toBeInTheDocument();
    expect(screen.getByTestId("verified-answer-reveal")).toBeInTheDocument();
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
        "Ask a general question, or ask about your company documents for a cited answer.",
      ),
    ).toBeInTheDocument();
  });
});

describe("AnswerSurface paragraph citations", () => {
  afterEach(() => {
    cleanup();
  });

  it("puts each mapped citation after its own paragraph", () => {
    renderSurface({
      answerOrigin: "company_documents",
      answer: "Refunds close in 30 days.\n\nAppeals go to finance.",
      citations: [
        {
          citation_id: "cite-a",
          citation_index: 0,
          chunk_id: "chunk-a",
          provenance: {},
          source_unavailable: false,
          paragraph_index: 0,
          document_title: "AI Agents",
          pdf_page_number: 25,
        },
        {
          citation_id: "cite-b",
          citation_index: 1,
          chunk_id: "chunk-b",
          provenance: {},
          source_unavailable: false,
          paragraph_index: 1,
          document_title: "AI Agents",
          pdf_page_number: 40,
        },
      ],
    });
    const blocks = screen.getAllByTestId("paragraph-citations");
    expect(blocks).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: "Citation 0, AI Agents · PDF page 25" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Citation 1, AI Agents · PDF page 40" }),
    ).toBeInTheDocument();
    expect(blocks[0]).toHaveTextContent("PDF page 25");
    expect(blocks[0]).not.toHaveTextContent("PDF page 40");
    expect(blocks[1]).toHaveTextContent("PDF page 40");
    expect(blocks[1]).not.toHaveTextContent("PDF page 25");
  });

  it("can show two source chips on one paragraph", () => {
    renderSurface({
      answerOrigin: "company_documents",
      answer: "Refunds close in 30 days.",
      citations: [
        {
          citation_id: "cite-a",
          citation_index: 0,
          chunk_id: "chunk-a",
          provenance: {},
          source_unavailable: false,
          paragraph_index: 0,
          document_title: "Policy",
          pdf_page_number: 10,
        },
        {
          citation_id: "cite-b",
          citation_index: 1,
          chunk_id: "chunk-b",
          provenance: {},
          source_unavailable: false,
          paragraph_index: 0,
          document_title: "Handbook",
          pdf_page_number: 11,
        },
      ],
    });
    const row = screen.getByTestId("paragraph-citations");
    expect(
      screen.getByRole("button", { name: "Citation 0, Policy · PDF page 10" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Citation 1, Handbook · PDF page 11" }),
    ).toBeInTheDocument();
    expect(row.querySelectorAll("button")).toHaveLength(2);
  });

  it("keeps unmapped citations in the legacy footer", () => {
    renderSurface({
      answerOrigin: "company_documents",
      answer: "Refunds close in 30 days.",
      citations: [
        {
          citation_id: "cite-legacy",
          citation_index: 3,
          chunk_id: "chunk-l",
          provenance: {},
          source_unavailable: false,
          paragraph_index: null,
          document_title: "AI Agents",
          pdf_page_number: 25,
        },
      ],
    });
    expect(
      screen.getByText("Legacy run sources (not mapped to a paragraph)"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("paragraph-citations")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Citation 3, AI Agents · PDF page 25",
      }),
    ).toBeInTheDocument();
  });

  it("hides chips until the paced-reveal paragraph is fully visible", () => {
    renderSurface({
      answerOrigin: "company_documents",
      answer: "Refunds close in 30 days.\n\nAppeals go to finance.",
      visibleAnswer: "Refunds close",
      revealing: true,
      citations: [
        {
          citation_id: "cite-a",
          citation_index: 0,
          chunk_id: "chunk-a",
          provenance: {},
          source_unavailable: false,
          paragraph_index: 0,
          document_title: "AI Agents",
          pdf_page_number: 25,
        },
      ],
    });
    expect(screen.getByText("Refunds close")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Citation 0/ })).toBeNull();
  });

  it("uses historical message citations instead of the live run list", () => {
    renderSurface({
      messages: [
        {
          message_id: "a1",
          role: "assistant",
          content: "Historical refunds close in 30 days.",
          created_at: "2026-08-27T11:00:00Z",
          citations: [
            {
              citation_id: "hist-1",
              citation_index: 0,
              chunk_id: "chunk-h",
              provenance: {},
              source_unavailable: false,
              paragraph_index: 0,
              document_title: "History Book",
              pdf_page_number: 8,
            },
          ],
        },
      ],
      question: "",
      answer: "",
      terminal: null,
      citations: [
        {
          citation_id: "live-secret",
          citation_index: 9,
          chunk_id: "chunk-live",
          provenance: {},
          source_unavailable: false,
          paragraph_index: 0,
          document_title: "Live Book",
          pdf_page_number: 99,
        },
      ],
    });
    expect(
      screen.getByRole("button", {
        name: "Citation 0, History Book · PDF page 8",
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Live Book")).not.toBeInTheDocument();
  });
});

describe("answerTerminalNote", () => {
  it("explains an empty deadline partial instead of kept-token copy", () => {
    expect(answerTerminalNote("partial", "", "deadline_exhausted")).toBe(
      EMPTY_DEADLINE_PARTIAL_COPY,
    );
    expect(answerTerminalNote("partial", "Hello.", "deadline_exhausted")).toBe(
      "Partial answer. Verified tokens are kept.",
    );
    expect(answerTerminalNote("partial", "")).toBe(
      "Partial answer. Verified tokens are kept.",
    );
  });
});

describe("transcriptTextMatches", () => {
  it("treats Python html.escape apostrophes as the live decoded string", () => {
    expect(
      transcriptTextMatches("the question&#x27;s scope", "the question's scope"),
    ).toBe(true);
  });

  it("does not match an empty live string to persisted history", () => {
    expect(transcriptTextMatches("Previous verified answer.", "")).toBe(false);
  });
});
