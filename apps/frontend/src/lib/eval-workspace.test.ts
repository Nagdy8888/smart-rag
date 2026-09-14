import { describe, expect, it } from "vitest";
import {
  boundedPassagePreview,
  citationCompareAllowed,
  evalAiRequestBody,
  evalApproveBlockedReason,
  evalCaseListLabel,
  evalGoldPageCaption,
  examPollIntervalMs,
  examRecallHeadline,
  filterEvalCasesByGoldState,
  holdoutCannotRun,
  isExamActive,
  isExamTerminal,
  normalizeEvalQuestion,
  pdfEvalCapability,
  quizScoreDecision,
  shortEvalHash,
  showSaveToQuizConvenience,
  toggleQuizGoldChunk,
} from "./eval-workspace";

describe("eval workspace helpers", () => {
  it("hides the tab unless meta capability is true", () => {
    expect(pdfEvalCapability(null)).toBe(false);
    expect(pdfEvalCapability({ pdf_eval_workspace: false })).toBe(false);
    expect(pdfEvalCapability({ pdf_eval_workspace: true })).toBe(true);
  });

  it("sends only the question to the paid Ask body", () => {
    expect(evalAiRequestBody("What is Hybrid?")).toEqual({
      message: "What is Hybrid?",
    });
    expect(evalAiRequestBody("What is Hybrid?")).not.toHaveProperty(
      "expected_answer",
    );
  });

  it("forbids citation compare before completed and holdout runs", () => {
    expect(citationCompareAllowed(null)).toBe(false);
    expect(citationCompareAllowed("error")).toBe(false);
    expect(citationCompareAllowed("completed")).toBe(true);
    expect(holdoutCannotRun("development")).toBe(false);
    expect(holdoutCannotRun("holdout")).toBe(true);
  });

  it("shows Save to quiz only for owner/admin when capability is on", () => {
    expect(showSaveToQuizConvenience("member", { pdf_eval_workspace: true })).toBe(
      false,
    );
    expect(showSaveToQuizConvenience("viewer", { pdf_eval_workspace: true })).toBe(
      false,
    );
    expect(showSaveToQuizConvenience("owner", { pdf_eval_workspace: false })).toBe(
      false,
    );
    expect(showSaveToQuizConvenience("admin", { pdf_eval_workspace: true })).toBe(
      true,
    );
  });

  it("normalizes questions like hosted duplicate detection", () => {
    expect(normalizeEvalQuestion("What is LCEL?")).toBe("what is lcel");
    expect(normalizeEvalQuestion("  What   is LCEL??")).toBe("what is lcel");
  });

  it("blocks scoring a newly saved draft against the creating run", () => {
    const created = new Set(["case-new"]);
    const blocked = quizScoreDecision({
      terminal: "completed",
      selectedCaseId: "case-new",
      reviewStatus: "draft",
      humanApproved: false,
      selectedQuestion: "What is LCEL?",
      currentQuestion: "What is LCEL?",
      createdFromThisRun: created,
    });
    expect(blocked.allowed).toBe(false);
    expect(blocked.reason).toContain("Newly saved drafts");
    const allowed = quizScoreDecision({
      terminal: "completed",
      selectedCaseId: "case-old",
      reviewStatus: "approved",
      humanApproved: true,
      selectedQuestion: "What is LCEL?",
      currentQuestion: "What is LCEL?",
      createdFromThisRun: created,
    });
    expect(allowed.allowed).toBe(true);
  });

  it("caps gold suggestions at three chunks", () => {
    const first = toggleQuizGoldChunk(["a", "b", "c"], "d");
    expect(first.blocked).toBe(true);
    expect(first.next).toEqual(["a", "b", "c"]);
    const removed = toggleQuizGoldChunk(["a", "b", "c"], "b");
    expect(removed.next).toEqual(["a", "c"]);
  });

  it("filters gold state and blocks stale or empty approve", () => {
    const rows = [{ gold_stale: false }, { gold_stale: true }];
    expect(filterEvalCasesByGoldState(rows, "stale")).toEqual([{ gold_stale: true }]);
    expect(filterEvalCasesByGoldState(rows, "current")).toEqual([{ gold_stale: false }]);
    expect(
      evalApproveBlockedReason({ goldStale: true, goldCount: 2, unsavedGold: false }),
    ).toContain("Stale gold");
    expect(
      evalApproveBlockedReason({ goldStale: false, goldCount: 0, unsavedGold: false }),
    ).toContain("1–3");
    expect(
      evalApproveBlockedReason({ goldStale: false, goldCount: 1, unsavedGold: false }),
    ).toBeNull();
    expect(
      evalCaseListLabel({
        query_class: "factual_definition",
        split: "development",
        review_status: "draft",
        human_approved: false,
      }),
    ).toBe("factual_definition · development · draft");
    expect(boundedPassagePreview("a".repeat(300)).endsWith("…")).toBe(true);
    expect(evalGoldPageCaption({ pageLabel: "iv", pageNumber: 4 })).toBe("iv");
    expect(evalGoldPageCaption({ pageLabel: null, pageNumber: 2 })).toBe("PDF page 2");
  });

  it("builds the official Recall@10 headline and poll backoff", () => {
    expect(
      examRecallHeadline({ hitCount: 8, caseCount: 10, ratio: 0.8 }),
    ).toBe("All required gold chunks in the production Hybrid top 10: 8 of 10 (80%)");
    expect(shortEvalHash("abcdef0123456789")).toBe("abcdef01");
    expect(shortEvalHash(null)).toBe("unknown");
    expect(isExamActive("queued")).toBe(true);
    expect(isExamActive("running")).toBe(true);
    expect(isExamTerminal("succeeded")).toBe(true);
    expect(isExamTerminal("failed")).toBe(true);
    expect(isExamActive("succeeded")).toBe(false);
    expect(examPollIntervalMs(1)).toBe(2_000);
    expect(examPollIntervalMs(4)).toBe(15_000);
  });
});
