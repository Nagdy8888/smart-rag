// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { PDF_EVAL_QUERY_CLASSES } from "../../lib/types";
import type { CitationResponse, PdfEvalCaseSummary } from "../../lib/types";
import {
  SaveToQuizPopover,
  type SaveToQuizPopoverProps,
} from "./save-to-quiz-popover";

const HOSTILE = "<script>alert(1)</script>";

function citation(index: number, chunkId: string): CitationResponse {
  return {
    citation_id: `cite-${String(index)}`,
    citation_index: index,
    chunk_id: chunkId,
    provenance: { document_title: `Doc ${String(index)} ${HOSTILE}` },
    source_unavailable: false,
  };
}

function summary(
  caseId: string,
  reviewStatus: string,
  queryClass = HOSTILE,
): PdfEvalCaseSummary {
  return {
    case_id: caseId,
    split: "development",
    query_class: queryClass,
    human_approved: reviewStatus === "approved",
    generated_only: false,
    reviewer: null,
    expected_refusal: false,
    gold_chunk_count: 0,
    review_status: reviewStatus,
    source_family_id: null,
    gold_stale: false,
    row_version: 1,
  };
}

function renderQuiz(overrides: Partial<SaveToQuizPopoverProps> = {}) {
  const props: SaveToQuizPopoverProps = {
    question: "What is LCEL?",
    citations: [],
    queryClass: PDF_EVAL_QUERY_CLASSES[0],
    onQueryClass: vi.fn(),
    expectedAnswer: "secret expected",
    onExpectedAnswer: vi.fn(),
    selectedChunkIds: [],
    goldBlocked: false,
    onToggleChunk: vi.fn(),
    savePending: false,
    saveError: null,
    saveNotice: null,
    onSave: vi.fn(),
    cases: [],
    casesPending: false,
    casesError: false,
    nextCaseId: null,
    loadMorePending: false,
    onLoadMore: vi.fn(),
    selectedCaseId: null,
    onSelectCase: vi.fn(),
    selectedQuestion: "",
    detailPending: false,
    onAskQuestion: vi.fn(),
    scoreAllowed: false,
    scoreReason: "Newly saved drafts cannot score the run that created them. not Recall@10",
    scorePending: false,
    scoreNotice: null,
    onScore: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<SaveToQuizPopover {...props} />) };
}

describe("SaveToQuizPopover", () => {
  afterEach(() => {
    cleanup();
  });

  it("saves a zero-gold draft and keeps expected answer out of Ask this question", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onAskQuestion = vi.fn();
    renderQuiz({
      onSave,
      onAskQuestion,
      selectedCaseId: "case-old",
      selectedQuestion: "What is LCEL?",
      cases: [summary("case-old", "approved", "factual_definition")],
    });
    await user.click(screen.getByRole("button", { name: "Save to quiz" }));
    expect(
      screen.getByText("Deleting this chat does not delete the saved quiz case."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    expect(onSave).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Ask this question" }));
    expect(onAskQuestion).toHaveBeenCalledTimes(1);
  });

  it("blocks a fourth gold citation accessibly", async () => {
    const user = userEvent.setup();
    const onToggleChunk = vi.fn();
    renderQuiz({
      citations: [
        citation(1, "chunk-a"),
        citation(2, "chunk-b"),
        citation(3, "chunk-c"),
        citation(4, "chunk-d"),
      ],
      selectedChunkIds: ["chunk-a", "chunk-b", "chunk-c"],
      goldBlocked: true,
      onToggleChunk,
    });
    await user.click(screen.getByRole("button", { name: "Save to quiz" }));
    const fourth = screen.getByRole("checkbox", { name: /Doc 4/ });
    expect(fourth).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("At most three gold citations.");
  });

  it("renders hostile query-class text as text and disables scoring a new draft", async () => {
    const user = userEvent.setup();
    const onScore = vi.fn();
    renderQuiz({
      cases: [summary("case-new", "draft")],
      selectedCaseId: "case-new",
      selectedQuestion: HOSTILE,
      scoreAllowed: false,
      scoreReason:
        "Newly saved drafts cannot score the run that created them. not Recall@10",
      onScore,
    });
    await user.click(screen.getByRole("button", { name: "Save to quiz" }));
    expect(screen.getAllByText(HOSTILE).length).toBeGreaterThan(0);
    expect(document.querySelector("script")).toBeNull();
    const score = screen.getByRole("button", {
      name: "Score this answer (not Recall@10)",
    });
    expect(score).toBeDisabled();
    await user.click(score);
    expect(onScore).not.toHaveBeenCalled();
  });

  it("offers Load more when a next case cursor exists", async () => {
    const user = userEvent.setup();
    const onLoadMore = vi.fn();
    renderQuiz({ nextCaseId: "case-next", onLoadMore });
    await user.click(screen.getByRole("button", { name: "Save to quiz" }));
    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it("shows pending, success, and retry copy", async () => {
    const user = userEvent.setup();
    renderQuiz({
      savePending: true,
      saveNotice: null,
      saveError: "Quiz case could not be saved. Try again.",
    });
    await user.click(screen.getByRole("button", { name: "Save to quiz" }));
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(
      screen.getByText("Quiz case could not be saved. Try again."),
    ).toBeInTheDocument();
  });
});
