// @vitest-environment jsdom

import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { PDF_EVAL_QUERY_CLASSES } from "../../lib/types";
import type { CitationResponse, PdfEvalCaseSummary } from "../../lib/types";
import {
  SaveToQuizSheet,
  type SaveToQuizSheetProps,
} from "./save-to-quiz-sheet";

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
  queryClass = "factual_definition",
  goldChunkCount = 0,
): PdfEvalCaseSummary {
  return {
    case_id: caseId,
    split: "development",
    query_class: queryClass,
    human_approved: reviewStatus === "approved",
    generated_only: false,
    reviewer: null,
    expected_refusal: false,
    gold_chunk_count: goldChunkCount,
    review_status: reviewStatus,
    source_family_id: null,
    gold_stale: false,
    row_version: 1,
  };
}

function renderQuiz(overrides: Partial<SaveToQuizSheetProps> = {}) {
  const props: SaveToQuizSheetProps = {
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
    onRetryCases: vi.fn(),
    nextCaseId: null,
    loadMorePending: false,
    loadMoreError: false,
    onLoadMore: vi.fn(),
    selectedCaseId: null,
    onSelectCase: vi.fn(),
    selectedQuestion: "",
    detailPending: false,
    detailError: false,
    onRetryDetail: vi.fn(),
    onAskQuestion: vi.fn(),
    scoreAllowed: false,
    scoreReason: "Newly saved drafts cannot score the run that created them. not Recall@10",
    scorePending: false,
    scoreNotice: null,
    scoreError: null,
    onScore: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<SaveToQuizSheet {...props} />) };
}

/**
 * Open the Save to quiz sheet from the footer trigger.
 *
 * @param user - Testing Library user.
 */
async function openSheet(
  user: ReturnType<typeof userEvent.setup>,
): Promise<HTMLElement> {
  await user.click(screen.getByRole("button", { name: "Save to quiz" }));
  return screen.getByRole("dialog", { name: "Save to quiz" });
}

describe("SaveToQuizSheet", () => {
  afterEach(() => {
    cleanup();
  });

  it("opens a dialog on New case, supports tab keys, and restores trigger focus", async () => {
    const user = userEvent.setup();
    renderQuiz();
    const trigger = screen.getByRole("button", { name: "Save to quiz" });
    expect(trigger).toHaveAttribute("data-action-id", "ask.quiz.save");
    await user.click(trigger);
    const newTab = screen.getByRole("tab", { name: "New case" });
    const savedTab = screen.getByRole("tab", { name: "Saved cases" });
    expect(newTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveAttribute(
      "aria-labelledby",
      newTab.id,
    );
    newTab.focus();
    await user.keyboard("{ArrowRight}");
    expect(savedTab).toHaveAttribute("aria-selected", "true");
    expect(savedTab).toHaveFocus();
    await user.keyboard("{Home}");
    expect(newTab).toHaveAttribute("aria-selected", "true");
    expect(newTab).toHaveFocus();
    await user.keyboard("{End}");
    expect(savedTab).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowLeft}");
    expect(newTab).toHaveAttribute("aria-selected", "true");
    await user.click(savedTab);
    expect(savedTab).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
    await user.click(trigger);
    expect(screen.getByRole("tab", { name: "New case" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("closes from the header Close control", async () => {
    const user = userEvent.setup();
    renderQuiz();
    const trigger = screen.getByRole("button", { name: "Save to quiz" });
    const dialog = await openSheet(user);
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger).toHaveFocus();
  });

  it("saves a zero-source draft and keeps expected answer out of Ask this question", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onAskQuestion = vi.fn();
    renderQuiz({
      onSave,
      onAskQuestion,
      selectedCaseId: "case-old",
      selectedQuestion: "What is LCEL?",
      cases: [summary("case-old", "approved", "factual_definition", 2)],
    });
    await openSheet(user);
    expect(
      screen.getByText("Deleting this chat does not delete the saved quiz case."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "For reviewers only. It is never sent when this question is asked again.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Question from this run" })).toBeNull();
    expect(screen.getByLabelText("Question type")).toHaveValue("factual_definition");
    expect(
      screen.getByRole("option", { name: "Direct fact or definition" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save quiz case" }));
    expect(onSave).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("tab", { name: "Saved cases" }));
    await user.click(screen.getByRole("button", { name: "Ask this question" }));
    expect(onAskQuestion).toHaveBeenCalledTimes(1);
    expect(onAskQuestion.mock.calls[0]).toEqual([]);
    expect(screen.queryByRole("dialog")).toBeNull();
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
    await openSheet(user);
    const fourth = screen.getByRole("checkbox", { name: /Doc 4/ });
    expect(fourth).toBeDisabled();
    expect(
      screen.getByText("Maximum 3 sources selected. Remove one to choose another."),
    ).toBeInTheDocument();
    expect(screen.getByText("3 of 3 selected")).toBeInTheDocument();
    const first = screen.getByRole("checkbox", { name: /Doc 1/ });
    expect(first).not.toBeDisabled();
    await user.click(first);
    expect(onToggleChunk).toHaveBeenCalledWith("chunk-a");
  });

  it("renders hostile query-class text as text and disables scoring a new draft", async () => {
    const user = userEvent.setup();
    const onScore = vi.fn();
    renderQuiz({
      question: HOSTILE,
      cases: [summary("case-new", "draft", HOSTILE)],
      selectedCaseId: "case-new",
      selectedQuestion: HOSTILE,
      scoreAllowed: false,
      scoreReason:
        "Newly saved drafts cannot score the run that created them. not Recall@10",
      onScore,
    });
    await openSheet(user);
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getAllByText(HOSTILE).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("tab", { name: "Saved cases" }));
    expect(screen.getAllByText(HOSTILE).length).toBeGreaterThan(0);
    const score = screen.getByRole("button", {
      name: "Score this answer (not Recall@10)",
    });
    expect(score).toBeDisabled();
    expect(
      screen.getByText(
        "Newly saved drafts cannot score the run that created them. not Recall@10",
      ),
    ).toBeInTheDocument();
    await user.click(score);
    expect(onScore).not.toHaveBeenCalled();
  });

  it("shows pending, success, and retry copy", async () => {
    const user = userEvent.setup();
    renderQuiz({
      savePending: true,
      saveNotice: null,
      saveError: "Quiz case could not be saved. Try again.",
    });
    await openSheet(user);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    const error = screen.getByText("Quiz case could not be saved. Try again.");
    expect(error.closest("p")).toHaveAttribute("data-kind", "error");
    expect(error.closest("p")).toHaveAttribute("role", "alert");
  });

  it("shows save success and switches to saved cases", async () => {
    const user = userEvent.setup();
    renderQuiz({
      saveNotice: "Quiz draft saved. It is not a quality score for this answer.",
    });
    await openSheet(user);
    const notice = screen.getByText(
      "Quiz draft saved. It is not a quality score for this answer.",
    );
    expect(notice.closest("p")).toHaveAttribute("data-kind", "success");
    await user.click(screen.getByRole("button", { name: "View saved cases" }));
    expect(screen.getByRole("tab", { name: "Saved cases" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("shows loading saved cases", async () => {
    const user = userEvent.setup();
    renderQuiz({ casesPending: true });
    await openSheet(user);
    await user.click(screen.getByRole("tab", { name: "Saved cases" }));
    expect(screen.getByText("Loading saved cases…")).toBeInTheDocument();
  });

  it("retries a failed saved-case list", async () => {
    const user = userEvent.setup();
    const onRetryCases = vi.fn();
    renderQuiz({ casesError: true, onRetryCases });
    await openSheet(user);
    await user.click(screen.getByRole("tab", { name: "Saved cases" }));
    expect(screen.getByText("Saved cases could not load.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetryCases).toHaveBeenCalledTimes(1);
  });

  it("offers Create a case from the empty saved list", async () => {
    const user = userEvent.setup();
    renderQuiz({ cases: [] });
    await openSheet(user);
    await user.click(screen.getByRole("tab", { name: "Saved cases" }));
    expect(screen.getByText("No saved cases yet")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create a case" }));
    expect(screen.getByRole("tab", { name: "New case" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("selects a saved case and retries detail", async () => {
    const user = userEvent.setup();
    const onSelectCase = vi.fn();
    const onRetryDetail = vi.fn();
    renderQuiz({
      cases: [summary("case-old", "approved", "factual_definition", 2)],
      selectedCaseId: "case-old",
      detailError: true,
      onSelectCase,
      onRetryDetail,
    });
    await openSheet(user);
    await user.click(screen.getByRole("tab", { name: "Saved cases" }));
    expect(screen.getByText("Factual definition")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("2 sources")).toBeInTheDocument();
    const row = screen.getByRole("button", { name: /Factual definition/ });
    expect(row).toHaveAttribute("aria-current", "true");
    await user.click(row);
    expect(onSelectCase).toHaveBeenCalledWith("case-old");
    expect(screen.getByText("This case could not load.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetryDetail).toHaveBeenCalledTimes(1);
  });

  it("shows detail loading copy", async () => {
    const user = userEvent.setup();
    renderQuiz({
      cases: [summary("case-old", "draft")],
      selectedCaseId: "case-old",
      detailPending: true,
    });
    await openSheet(user);
    await user.click(screen.getByRole("tab", { name: "Saved cases" }));
    expect(screen.getByText("Loading case…")).toBeInTheDocument();
  });

  it("offers Load more and keeps rows after a page error", async () => {
    const user = userEvent.setup();
    const onLoadMore = vi.fn();
    renderQuiz({
      nextCaseId: "case-next",
      loadMoreError: true,
      cases: [summary("case-old", "approved")],
      onLoadMore,
    });
    await openSheet(user);
    await user.click(screen.getByRole("tab", { name: "Saved cases" }));
    expect(screen.getByText("Factual definition")).toBeInTheDocument();
    expect(screen.getByText("More cases could not load. Try again.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(onLoadMore).toHaveBeenCalledTimes(1);
  });

  it("scores an allowed approved matching case", async () => {
    const user = userEvent.setup();
    const onScore = vi.fn();
    renderQuiz({
      cases: [summary("case-old", "approved")],
      selectedCaseId: "case-old",
      selectedQuestion: "What is LCEL?",
      scoreAllowed: true,
      scoreReason: "",
      scoreNotice: "Citation overlap 2 of 3 gold IDs (not Recall@10).",
      onScore,
    });
    await openSheet(user);
    await user.click(screen.getByRole("tab", { name: "Saved cases" }));
    const score = screen.getByRole("button", {
      name: "Score this answer (not Recall@10)",
    });
    expect(score).toBeEnabled();
    await user.click(score);
    expect(onScore).toHaveBeenCalledTimes(1);
    const notice = screen.getByText(
      "Citation overlap 2 of 3 gold IDs (not Recall@10).",
    );
    expect(notice.closest("p")).toHaveAttribute("data-kind", "success");
  });

  it("shows a distinct score failure", async () => {
    const user = userEvent.setup();
    renderQuiz({
      cases: [summary("case-old", "approved")],
      selectedCaseId: "case-old",
      selectedQuestion: "What is LCEL?",
      scoreAllowed: true,
      scoreError: "Citation overlap could not be scored. Try again.",
    });
    await openSheet(user);
    await user.click(screen.getByRole("tab", { name: "Saved cases" }));
    const error = screen.getByText("Citation overlap could not be scored. Try again.");
    expect(error.closest("p")).toHaveAttribute("data-kind", "error");
    expect(error.closest("p")).toHaveAttribute("role", "alert");
  });
});
