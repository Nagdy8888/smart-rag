import { describe, expect, it } from "vitest";
import type { PdfEvalCaseDetail, PdfEvalCaseSummary, PdfEvalStatus } from "../../lib/types";
import {
  datasetLabel,
  evalApproveUiReason,
  evalDetailsDirty,
  examRecallPercent,
  examStatusLabel,
  formatExamCompletedAt,
  metricCount,
  nextReviewCase,
  overviewGuidanceKind,
  queryClassLabel,
  reviewStatusLabel,
  reviewStatusTone,
  sourceCountLabel,
  sourceStatusLabel,
  sourceStatusTone,
} from "./evaluation-presenters";

function status(overrides: Partial<PdfEvalStatus> = {}): PdfEvalStatus {
  return {
    enabled: true,
    case_count: 1,
    revision: null,
    version_id: null,
    document_id: null,
    dataset_present: true,
    ...overrides,
  };
}

function summary(overrides: Partial<PdfEvalCaseSummary> = {}): PdfEvalCaseSummary {
  return {
    case_id: "case-1",
    split: "development",
    query_class: "factual_definition",
    human_approved: false,
    generated_only: true,
    reviewer: null,
    expected_refusal: false,
    gold_chunk_count: 1,
    review_status: "draft",
    source_family_id: null,
    gold_stale: false,
    row_version: 1,
    ...overrides,
  };
}

describe("evaluation presenters", () => {
  it("humanizes known tokens and passes unknown values through", () => {
    expect(queryClassLabel("factual_definition")).toBe("Factual definition");
    expect(queryClassLabel("<img src=x>")).toBe("<img src=x>");
    expect(datasetLabel("development")).toBe("Development");
    expect(datasetLabel("holdout")).toBe("holdout");
    expect(reviewStatusLabel("draft", false)).toBe("Draft");
    expect(reviewStatusLabel("approved", true)).toBe("Approved");
    expect(reviewStatusTone("rejected", false)).toBe("danger");
    expect(sourceStatusLabel(true)).toBe("Sources stale");
    expect(sourceStatusTone(false)).toBe("success");
    expect(sourceCountLabel(1)).toBe("1 source");
    expect(sourceCountLabel(2)).toBe("2 sources");
    expect(examStatusLabel("running")).toBe("Running");
  });

  it("uses an em dash for missing counts and zero only when explicit", () => {
    expect(metricCount(undefined)).toBe("—");
    expect(metricCount(0)).toBe("0");
    expect(metricCount(4)).toBe("4");
  });

  it("chooses overview guidance from explicit counts", () => {
    expect(overviewGuidanceKind(undefined)).toBe("empty");
    expect(overviewGuidanceKind(status({ case_count: 0 }))).toBe("empty");
    expect(overviewGuidanceKind(status({ stale_gold_count: 2, draft_count: 3 }))).toBe("stale");
    expect(overviewGuidanceKind(status({ stale_gold_count: 0, draft_count: 2 }))).toBe("drafts");
    expect(overviewGuidanceKind(status({ case_count: 2 }))).toBe("ready");
    expect(overviewGuidanceKind(status({ draft_count: 0, stale_gold_count: 0 }))).toBe("ready");
  });

  it("prefers stale then draft rows for the next review case", () => {
    const draft = summary({ case_id: "draft" });
    const stale = summary({ case_id: "stale", gold_stale: true, review_status: "approved" });
    const approved = summary({ case_id: "ok", review_status: "approved", human_approved: true });
    expect(nextReviewCase([draft, stale, approved])?.case_id).toBe("stale");
    expect(nextReviewCase([approved, draft])?.case_id).toBe("draft");
    expect(nextReviewCase([approved])?.case_id).toBe("ok");
    expect(nextReviewCase([])).toBeUndefined();
  });

  it("detects dirty details and prioritizes approve reasons", () => {
    const detail = {
      question: "Q?",
      expected_answer: "A",
      atomic_facts: ["one"],
      required_terms: ["term"],
      query_class: "factual_definition",
    } as Pick<
      PdfEvalCaseDetail,
      "question" | "expected_answer" | "atomic_facts" | "required_terms" | "query_class"
    >;
    expect(
      evalDetailsDirty({
        question: "Q?",
        expectedAnswer: "A",
        atomicFacts: "one",
        requiredTerms: "term",
        queryClass: "factual_definition",
        detail,
      }),
    ).toBe(false);
    expect(
      evalDetailsDirty({
        question: "Changed?",
        expectedAnswer: "A",
        atomicFacts: "one",
        requiredTerms: "term",
        queryClass: "factual_definition",
        detail,
      }),
    ).toBe(true);
    expect(
      evalApproveUiReason({
        detailsDirty: true,
        goldDirty: true,
        goldStale: true,
        goldCount: 0,
      }),
    ).toBe("Save case details before approval.");
    expect(
      evalApproveUiReason({
        detailsDirty: false,
        goldDirty: true,
        goldStale: false,
        goldCount: 1,
      }),
    ).toBe("Save source changes before approval.");
    expect(
      evalApproveUiReason({
        detailsDirty: false,
        goldDirty: false,
        goldStale: true,
        goldCount: 1,
      }),
    ).toBe(
      "Remap required sources from current passages before approval. Stale sources cannot be approved.",
    );
    expect(
      evalApproveUiReason({
        detailsDirty: false,
        goldDirty: false,
        goldStale: false,
        goldCount: 0,
      }),
    ).toBe("Select 1–3 current source passages before approval.");
    expect(
      evalApproveUiReason({
        detailsDirty: false,
        goldDirty: false,
        goldStale: false,
        goldCount: 2,
      }),
    ).toBeNull();
  });

  it("formats exam percent and completion time without inventing success", () => {
    expect(examRecallPercent({ hitCount: 4, caseCount: 4, ratio: 1 })).toBe(100);
    expect(examRecallPercent({ hitCount: 1, caseCount: 4, ratio: null })).toBe(25);
    expect(formatExamCompletedAt(null)).toBe("unknown");
    expect(formatExamCompletedAt("not-a-date")).toBe("not-a-date");
    expect(formatExamCompletedAt("2026-09-13T12:00:00+00:00")).not.toBe(
      "2026-09-13T12:00:00+00:00",
    );
  });
});
