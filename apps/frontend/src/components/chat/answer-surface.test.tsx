// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { MIXED_SCOPE_CLARIFICATION } from "../../lib/answer-origin";
import { EMPTY_DEADLINE_PARTIAL_COPY } from "../../lib/run-details";
import type { CitationResponse } from "../../lib/types";
import { createChatViewState } from "../../lib/chat-view";
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

  it("restores a recorded failure beside an unanswered historical question", () => {
    renderSurface({ question: "", answer: "", terminal: null, messages: [{
      message_id: "failed-question", role: "user", content: "Compare two public standards",
      created_at: "2026-10-27T12:00:00Z", run_id: "failed-run", run_status: "failed",
    }] });
    expect(screen.getByText("This question could not be completed. No answer was saved.")).toBeInTheDocument();
  });

  it("does not infer failure from an older question without recorded status", () => {
    renderSurface({ question: "", answer: "", terminal: null, messages: [{
      message_id: "old-question", role: "user", content: "An old question",
      created_at: "2026-10-27T12:00:00Z", run_id: "old-run",
    }] });
    expect(screen.queryByText("This question could not be completed. No answer was saved.")).not.toBeInTheDocument();
  });

  it("renders each catalog origin label without inferring from the route", () => {
    const labels = [
      ["general_knowledge", "General knowledge"],
      ["company_documents", "Company documents"],
      ["user_supplied_text", "Your text"],
      ["deterministic", "Assistant"],
      ["ambiguous", "Needs clarification"],
      ["web", "Web"],
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

  it("shows citations for company origin, web origin, and a null legacy origin", () => {
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
        answerOrigin="web"
      />,
    );
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

  it("keeps company page labels out of the chat until Sources opens", () => {
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
    expect(screen.queryByRole("button", { name: /^Citation / })).not.toBeInTheDocument();
    expect(screen.queryByText("AI agents")).not.toBeInTheDocument();
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

  it("renders a code answer as a snippet and keeps markup inert", () => {
    const { container } = renderSurface({
      answerOrigin: "company_documents",
      answer:
        '@tool def multiply(x: float, y: float) -> float: """Multiply.""" return x * y <img src=x onerror=alert(1)>',
    });
    const snippet = screen.getByTestId("answer-code-snippet");
    expect(snippet.querySelector("pre")).not.toBeNull();
    expect(snippet.textContent).toContain("def multiply");
    expect(snippet.textContent).toContain("\n");
    expect(snippet.textContent).toMatch(/python/i);
    expect(screen.getByRole("button", { name: "Copy python snippet" })).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders code and tables for general_knowledge without citation gating", () => {
    const { unmount } = renderSurface({
      answerOrigin: "general_knowledge",
      citations: [],
      answer: [
        "```python",
        "def hello():",
        "    return 1",
        "```",
      ].join("\n"),
    });
    expect(screen.getByTestId("answer-code-snippet")).toBeInTheDocument();
    expect(screen.queryByTestId("answer-citations")).not.toBeInTheDocument();
    unmount();

    renderSurface({
      answerOrigin: "general_knowledge",
      citations: [],
      answer: [
        "| Model | Score |",
        "| --- | --- |",
        "| Gemma | 72 |",
      ].join("\n"),
    });
    const table = screen.getByTestId("answer-table");
    expect(table.querySelector("table")).not.toBeNull();
    expect(table.textContent).toContain("Gemma");
  });

  it("formats prose lists and bold for non-citation origins", () => {
    const { container } = renderSurface({
      answerOrigin: "deterministic",
      citations: [],
      answer: ["Use **care**.", "", "- One", "- Two"].join("\n"),
    });
    expect(screen.getAllByTestId("answer-prose").length).toBeGreaterThan(0);
    expect(container.querySelector("strong")).toHaveTextContent("care");
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
  });

  it("renders a mixed bold/list/fence/table answer without a stray fence", () => {
    const { container } = renderSurface({
      answerOrigin: "general_knowledge",
      citations: [],
      answer: [
        "Use **bold** carefully.",
        "",
        "- Alpha",
        "- Beta",
        "",
        "```python",
        "def hello():",
        "    return 1",
        "",
        "```",
        "",
        "| Model | Score |",
        "| --- | --- |",
        "| Gemma | 72 |",
      ].join("\n"),
    });
    expect(container.querySelector("strong")).toHaveTextContent("bold");
    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    const snippet = screen.getByTestId("answer-code-snippet");
    expect(snippet.textContent).toContain("def hello");
    expect(snippet.textContent).not.toMatch(/```/);
    const table = screen.getByTestId("answer-table");
    expect(table.querySelector("table")).not.toBeNull();
    expect(table.textContent).toContain("Gemma");
    expect(container.textContent).not.toMatch(/```/);
  });

  it("renders an import listing as code and skips a fenced repeat of the table", () => {
    renderSurface({
      answerOrigin: "general_knowledge",
      citations: [],
      answer: [
        "| Name | Note |",
        "| --- | --- |",
        "| Alpha | First row |",
        "| Beta | Second row |",
        "",
        "Load the helpers before calling them.",
        "from pkg.mod import Widget",
        "12",
        "from pkg.other import Helper,",
        "ExtraName",
        "",
        "```",
        "Alpha",
        "Beta",
        "```",
      ].join("\n"),
    });
    expect(screen.getAllByTestId("answer-table")).toHaveLength(1);
    expect(screen.getAllByTestId("answer-code-snippet")).toHaveLength(1);
    const snippet = screen.getByTestId("answer-code-snippet");
    expect(snippet.textContent).toContain("from pkg.mod import Widget");
    expect(snippet.textContent).toContain("ExtraName");
    expect(snippet.textContent).not.toContain("Alpha");
    expect(screen.getByTestId("answer-prose").textContent).toContain(
      "Load the helpers",
    );
  });

  it("renders a pipe table as a table and keeps markup inert", () => {
    const { container } = renderSurface({
      answerOrigin: "company_documents",
      answer: [
        "Table 2-1 Selected models",
        "| Model | Payload |",
        "| --- | --- |",
        "| Gemma 2 | <img src=x onerror=alert(1)> |",
      ].join("\n"),
    });
    const table = screen.getByTestId("answer-table");
    expect(table.querySelector("table")).not.toBeNull();
    expect(table.textContent).toContain("Gemma 2");
    expect(table.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows Starting as soon as send begins, before a run id", () => {
    render(
      <AnswerSurface
        question="What is our refund policy?"
        answer=""
        citations={[]}
        terminal={null}
        starting
        hrefForCitation={() => undefined}
        onSelectCitation={vi.fn()}
      />,
    );
    expect(screen.getByText("What is our refund policy?")).toBeInTheDocument();
    expect(screen.getByTestId("run-progress-timeline")).toBeInTheDocument();
    expect(screen.getByText("Starting…")).toBeInTheDocument();
    expect(screen.queryByText("Preparing query")).not.toBeInTheDocument();
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
    expect(screen.getAllByText("Writing your answer").length).toBeGreaterThan(0);
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
        "Ask about your documents",
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
        "Ask about your documents",
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

  it("keeps a repeated question above its new answer instead of deduplicating another run", () => {
    renderSurface({
      messages: [
        {message_id:"old-user",role:"user",content:"Explain memory",created_at:"2026-10-22T01:00:00Z",run_id:"old"},
        {message_id:"old-answer",role:"assistant",content:"Prior explanation.",created_at:"2026-10-22T01:00:01Z",run_id:"old"},
      ],
      chat:{...createChatViewState("key"),runId:"new"},
      question:"Explain memory", answer:"Updated explanation.", terminal:"completed",
    });
    const questions=screen.getAllByText("Explain memory");
    expect(questions).toHaveLength(2);
    expect(questions[1]!.compareDocumentPosition(screen.getByText("Updated explanation.")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
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
        "Ask about your documents",
      ),
    ).toBeInTheDocument();
  });
});

describe("AnswerSurface paragraph citations", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders the explanation after a code fence inside the same paragraph", () => {
    renderSurface({answer:"Introduction to the example:\n```python\ndef widget():\n    return 1\n```\n**Explanation**\nThe function returns the integer one. This is the final sentence.",citations:[]});
    expect(screen.getByText("Introduction to the example:")).toBeInTheDocument();
    expect(screen.getByTestId("answer-code-snippet").querySelector("code")?.textContent).toContain("def widget");
    expect(screen.getByRole("heading",{name:"Explanation"})).toBeInTheDocument();
    expect(screen.getByText(/This is the final sentence/)).toBeInTheDocument();
  });

  it("decodes escaped code literals only once when splitting a mixed paragraph", () => {
    renderSurface({answer:'Example:\n```javascript\nconst entity = "&amp;amp;";\n```\nThe literal remains encoded.',citations:[]});
    expect(screen.getByTestId("answer-code-snippet").querySelector("code")?.textContent).toBe('const entity = "&amp;";');
  });

  it("renders every distinct figure, including UUIDs, without dropping surrounding prose", () => {
    const id = "a1111111-1111-4111-8111-111111111111";
    renderSurface({ answer: `First diagram. [[figure:${id}]]\nSecond diagram. [[figure:bbbb]]\n\nRepeated reference. [[figure:${id}]]`, citations: [] });
    expect(screen.getAllByTestId("answer-figure")).toHaveLength(2);
    expect(screen.getByText(/First diagram/)).toBeInTheDocument();
    expect(screen.getByText(/Second diagram/)).toBeInTheDocument();
    expect(screen.getByText(/Repeated reference/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("[[figure:");
  });

  it("shows a cited image even when the answer omitted its figure marker", () => {
    renderSurface({ answerOrigin: "company_documents", answer: "The diagram shows the controller.", citations: [{ ...CITATION, provenance: { content_kind: "figure", figure_id: "abcd" } }] });
    expect(screen.getByTestId("answer-figure")).toBeInTheDocument();
  });

  it("never treats marker examples inside code as images or accepts a model URL", () => {
    const { container } = renderSurface({ answer: '```python\nexample = "[[figure:abcd]]"\n```\n\n[[figure:https://evil.example/image.png]]', citations: [] });
    expect(screen.queryByTestId("answer-figure")).not.toBeInTheDocument();
    expect(container.querySelector("code")?.textContent).toContain("[[figure:abcd]]");
    expect(container.querySelector("img")).toBeNull();
  });

  it("preserves prose paragraphs without turning explanations into list items", () => {
    const { container, unmount } = renderSurface({
      answer: "Refunds close in 30 days.\n\nAppeals go to finance.",
    });
    expect(container.querySelector("ol")).toBeNull();
    expect(container.querySelectorAll("ul > li[data-paragraph-index]")).toHaveLength(0);
    expect(container.querySelectorAll("[data-paragraph-index] p")).toHaveLength(2);
    expect(container.querySelectorAll("[data-paragraph-index]")).toHaveLength(2);
    unmount();
    const view = renderSurface({
      answer: "The window is 30 days. The request must be in writing.",
    });
    expect(view.container.querySelector("ol")).toBeNull();
    expect(view.container.querySelectorAll("[data-paragraph-index]")).toHaveLength(1);
    expect(view.container.querySelector("[data-answer-groups='true']")).toBeNull();
  });

  it("keeps multi-paragraph sources out of the chat", () => {
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
    expect(screen.queryByRole("region", { name: "Answer sources" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("answer-source-list")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Citation / })).not.toBeInTheDocument();
  });

  it("keeps multiple supporting citations behind Sources", () => {
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
    expect(screen.queryByTestId("answer-source-list")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Citation / })).not.toBeInTheDocument();
  });

  it("keeps legacy source lists behind Sources", () => {
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
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Citation / })).not.toBeInTheDocument();
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
    expect(screen.queryByRole("button", { name: /Citation 1/ })).toBeNull();
  });

  it("shows Sources (citation_count) for historical assistants without live chips", () => {
    const onOpenTurnSources = vi.fn();
    renderSurface({
      messages: [
        {
          message_id: "a1",
          role: "assistant",
          content: "Historical refunds close in 30 days.",
          created_at: "2026-08-27T11:00:00Z",
          run_id: "run-hist",
          citation_count: 1,
          source_kind: "company_document",
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
              evidence_excerpt: "should not render from list",
            },
          ],
        },
      ],
      question: "",
      answer: "",
      terminal: null,
      onOpenTurnSources,
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
    expect(screen.getByRole("button", { name: "Sources (1 citations)" })).toBeInTheDocument();
    expect(screen.queryByText("History Book")).not.toBeInTheDocument();
    expect(screen.queryByText("Live Book")).not.toBeInTheDocument();
    expect(screen.queryByText("should not render from list")).not.toBeInTheDocument();
    screen.getByRole("button", { name: "Sources (1 citations)" }).click();
    expect(onOpenTurnSources).toHaveBeenCalledWith("run-hist");
  });

  it("hides Sources for a historical general answer with citation_count 0", () => {
    renderSurface({
      messages: [
        {
          message_id: "a1",
          role: "assistant",
          content: "Paris is the capital of France.",
          created_at: "2026-08-27T11:00:00Z",
          run_id: "run-general",
          citation_count: 0,
          source_kind: null,
        },
      ],
      question: "",
      answer: "",
      terminal: null,
    });
    expect(screen.queryByRole("button", { name: /Sources/ })).toBeNull();
  });
});

describe("answerTerminalNote", () => {
  it("does not describe a refused answer as verified tokens", () => {
    expect(answerTerminalNote("partial", "Please try again.", "refused")).toBe(
      "An answer could not be verified.",
    );
  });
  it("explains an empty deadline partial instead of kept-token copy", () => {
    expect(answerTerminalNote("partial", "", "deadline_exhausted")).toBe(
      EMPTY_DEADLINE_PARTIAL_COPY,
    );
    expect(answerTerminalNote("partial", "Hello.", "deadline_exhausted")).toBe(
      "This answer is partial. Only verified content is shown.",
    );
    expect(answerTerminalNote("partial", "")).toBe(
      "This answer is partial. Only verified content is shown.",
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


describe("restored Web references", () => {
  afterEach(cleanup);
  it("opens the correct historical run from structured and legacy references", () => {
    const select = vi.fn();
    const web: CitationResponse = { citation_id: "web-c", citation_index: 0, chunk_id: null,
      source_kind: "web", source_unavailable: false, provenance: { title: "RFC 6585" } };
    renderSurface({ question: "", answer: "", messages: [{ message_id: "m", role: "assistant",
      content: "Supported. [[cite:0]] Legacy. [0]", created_at: "2026-10-28T00:00:00Z",
      run_id: "historical-run", answer_origin: "web", citation_count: 1 }],
      historyCitations: { "historical-run": [web] }, onSelectTurnCitation: select });
    const buttons = screen.getAllByRole("button", { name: "Citation 1, RFC 6585" });
    buttons[0]!.click();
    expect(select.mock.calls[0]?.[0]).toBe("historical-run");
    expect(select.mock.calls[0]?.[1].citation_id).toBe("web-c");
    expect(screen.queryByText(/\[\[cite:/)).not.toBeInTheDocument();
    expect(buttons).toHaveLength(2);
  });
});
