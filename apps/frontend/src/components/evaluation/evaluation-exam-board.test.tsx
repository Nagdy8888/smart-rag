// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { writeEvalExamPointer } from "../../lib/eval-exam-pointer";
import type {
  PdfEvalEmptyDataset,
  PdfEvalExamReport,
  PdfEvalExamStatus,
} from "../../lib/types";
import { EvaluationExamBoard } from "./evaluation-exam-board";

const fetchPdfEvalLatestReport = vi.fn();
const fetchPdfEvalExam = vi.fn();
const startPdfEvalExam = vi.fn();
const cancelPdfEvalExam = vi.fn();
const listPdfEvalExamCases = vi.fn();

vi.mock("../../lib/eval-workspace", async () => {
  const actual = await vi.importActual<typeof import("../../lib/eval-workspace")>(
    "../../lib/eval-workspace",
  );
  return {
    ...actual,
    examPollIntervalMs: () => 20,
  };
});

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    fetchPdfEvalLatestReport: (...args: unknown[]) => fetchPdfEvalLatestReport(...args),
    fetchPdfEvalExam: (...args: unknown[]) => fetchPdfEvalExam(...args),
    startPdfEvalExam: (...args: unknown[]) => startPdfEvalExam(...args),
    cancelPdfEvalExam: (...args: unknown[]) => cancelPdfEvalExam(...args),
    listPdfEvalExamCases: (...args: unknown[]) => listPdfEvalExamCases(...args),
  };
});

const AUTH = { accessToken: "jwt-token" };
const DATASET = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789";
const CANDIDATE = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210";

function absentReport(): PdfEvalExamReport {
  return {
    present: false,
    holdout_opened: false,
    exam_run_id: null,
    split: "development",
    dataset_hash: null,
    case_count: null,
    hit_count: null,
    hybrid_recall_at_10: null,
    gates_pass: null,
    created_at: null,
  };
}

function passReport(overrides: Partial<PdfEvalExamReport> = {}): PdfEvalExamReport {
  return {
    present: true,
    holdout_opened: false,
    exam_run_id: "exam-pass",
    split: "development",
    dataset_hash: DATASET,
    case_count: 4,
    hit_count: 4,
    hybrid_recall_at_10: 1,
    gates_pass: true,
    created_at: "2026-09-13T12:00:00+00:00",
    ...overrides,
  };
}

function examStatus(overrides: Partial<PdfEvalExamStatus> = {}): PdfEvalExamStatus {
  return {
    exam_run_id: "exam-1",
    split: "development",
    status: "queued",
    dataset_hash: DATASET,
    case_count: 4,
    completed_case_count: 0,
    holdout_opened: false,
    candidate_fingerprint: CANDIDATE,
    ...overrides,
  };
}

function emptyDatasetError(): Error & PdfEvalEmptyDataset {
  const error = new Error("empty_dataset") as Error & PdfEvalEmptyDataset;
  error.detail = "empty_dataset";
  error.draft_count = 3;
  error.approved_count = 0;
  error.rejected_count = 1;
  error.stale_gold_count = 2;
  error.live_count = 4;
  return error;
}

/**
 * Render the scoreboard with a fresh query client.
 *
 * @param ui - Element.
 * @returns Render result.
 */
function renderBoard(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

beforeEach(() => {
  fetchPdfEvalLatestReport.mockReset();
  fetchPdfEvalExam.mockReset();
  startPdfEvalExam.mockReset();
  cancelPdfEvalExam.mockReset();
  listPdfEvalExamCases.mockReset();
  fetchPdfEvalLatestReport.mockResolvedValue(absentReport());
  fetchPdfEvalExam.mockResolvedValue(examStatus());
  startPdfEvalExam.mockResolvedValue({
    exam_run_id: "exam-1",
    status: "queued",
    dataset_hash: DATASET,
    replayed: false,
    holdout_opened: false,
  });
  cancelPdfEvalExam.mockResolvedValue(
    examStatus({ status: "cancelled", completed_case_count: 1 }),
  );
  listPdfEvalExamCases.mockResolvedValue({
    exam_run_id: "exam-pass",
    items: [
      {
        case_id: "case-1",
        ordinal: 1,
        hit: true,
        gold_count: 2,
        ranked_hit_count: 2,
        latency_ms: 12,
      },
      {
        case_id: "case-2",
        ordinal: 2,
        hit: false,
        gold_count: 1,
        ranked_hit_count: 0,
        latency_ms: 9,
      },
    ],
    missed_count: 1,
  });
});

describe("EvaluationExamBoard", () => {
  it("shows present=false without a gates_pass label", async () => {
    renderBoard(
      <EvaluationExamBoard auth={AUTH} approvedCount={5} onOpenCase={vi.fn()} />,
    );
    expect(await screen.findByText("No official result yet")).toBeInTheDocument();
    expect(screen.queryByText("Retrieve gates passed.")).toBeNull();
    expect(screen.queryByText(/gates_pass/i)).toBeNull();
    expect(screen.getByText("What Recall@10 means")).toBeInTheDocument();
    fireEvent.click(screen.getByText("What Recall@10 means"));
    expect(
      screen.getByText(/All required gold chunks in the production Hybrid top 10/),
    ).toBeInTheDocument();
  });

  it("shows insufficient-dataset counts and never labels gates_pass", async () => {
    startPdfEvalExam.mockRejectedValue(emptyDatasetError());
    renderBoard(<EvaluationExamBoard auth={AUTH} onOpenCase={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Run development exam" }));
    expect(
      await screen.findByText(/Not enough approved current gold to start an exam/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Approved 0, drafts 3, stale gold 2/)).toBeInTheDocument();
    expect(screen.queryByText("Retrieve gates passed.")).toBeNull();
    expect(screen.queryByText(/gates_pass/i)).toBeNull();
    expect(screen.queryByText(/Official Recall@10 did not/)).toBeNull();
  });

  it("renders a passing official report with production-corpus copy", async () => {
    fetchPdfEvalLatestReport.mockResolvedValue(passReport());
    renderBoard(
      <EvaluationExamBoard auth={AUTH} approvedCount={4} onOpenCase={vi.fn()} />,
    );
    expect(
      await screen.findByText(
        "All required gold chunks in the production Hybrid top 10: 4 of 4 (100%)",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Retrieve gates passed.")).toBeInTheDocument();
    expect(screen.getByText(/4 approved in the workspace/)).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /Open case 1 · hit · 2 sources/ }),
    ).toBeInTheDocument();
    expect(screen.queryByText("SECRET_QUESTION")).toBeNull();
    expect(screen.queryByText("SECRET_ANSWER")).toBeNull();
    fireEvent.click(screen.getByText("Technical details"));
    expect(screen.getByText(/Dataset abcdef01/)).toBeInTheDocument();
  });

  it("renders failed retrieve gates without inventing a freeze control", async () => {
    fetchPdfEvalLatestReport.mockResolvedValue(
      passReport({
        hit_count: 1,
        hybrid_recall_at_10: 0.25,
        gates_pass: false,
      }),
    );
    renderBoard(<EvaluationExamBoard auth={AUTH} onOpenCase={vi.fn()} />);
    expect(
      await screen.findByText(
        "All required gold chunks in the production Hybrid top 10: 1 of 4 (25%)",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Degraded or failed retrieve gates/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /freeze/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /holdout/i })).toBeNull();
  });

  it("polls queued then running then succeeded and keeps count-only rows", async () => {
    fetchPdfEvalLatestReport
      .mockResolvedValueOnce(absentReport())
      .mockResolvedValue(passReport());
    fetchPdfEvalExam
      .mockResolvedValueOnce(examStatus({ status: "queued", completed_case_count: 0 }))
      .mockResolvedValueOnce(examStatus({ status: "running", completed_case_count: 2 }))
      .mockResolvedValue(
        examStatus({ status: "succeeded", completed_case_count: 4 }),
      );
    renderBoard(<EvaluationExamBoard auth={AUTH} onOpenCase={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Run development exam" }));
    expect(await screen.findByText(/development exam queued/)).toBeInTheDocument();
    expect(await screen.findByText(/development exam running: 2 of 4/)).toBeInTheDocument();
    expect(await screen.findByText(/development exam succeeded: 4 of 4/)).toBeInTheDocument();
    expect(
      await screen.findByText(
        "All required gold chunks in the production Hybrid top 10: 4 of 4 (100%)",
      ),
    ).toBeInTheDocument();
    expect(startPdfEvalExam).toHaveBeenCalledWith(
      AUTH,
      expect.objectContaining({
        split: "development",
        expected_dataset_hash: null,
      }),
    );
    expect(screen.queryByText("SECRET_QUESTION")).toBeNull();
  });

  it("reconnects an in-flight exam from the session pointer", async () => {
    writeEvalExamPointer({ examRunId: "exam-1", split: "development" });
    fetchPdfEvalExam.mockResolvedValue(
      examStatus({ status: "running", completed_case_count: 1 }),
    );
    renderBoard(<EvaluationExamBoard auth={AUTH} onOpenCase={vi.fn()} />);
    expect(await screen.findByText(/development exam running: 1 of 4/)).toBeInTheDocument();
    expect(fetchPdfEvalExam).toHaveBeenCalledWith(AUTH, "exam-1");
  });

  it("links a one-active conflict to the stored exam", async () => {
    startPdfEvalExam.mockRejectedValue(new Error("already_running"));
    renderBoard(<EvaluationExamBoard auth={AUTH} onOpenCase={vi.fn()} />);
    await screen.findByRole("button", { name: "Run development exam" });
    writeEvalExamPointer({ examRunId: "exam-1", split: "development" });
    fetchPdfEvalExam.mockResolvedValue(
      examStatus({ status: "running", completed_case_count: 3 }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Run development exam" }));
    expect(
      await screen.findByText(/Resume the active exam from this browser session/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resume progress" }));
    expect(await screen.findByText(/development exam running: 3 of 4/)).toBeInTheDocument();
  });

  it("does not invent an exam id when already_running has no pointer", async () => {
    startPdfEvalExam.mockRejectedValue(new Error("already_running"));
    renderBoard(<EvaluationExamBoard auth={AUTH} onOpenCase={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Run development exam" }));
    expect(
      await screen.findByText(/This browser has no resume id/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resume progress" })).toBeNull();
  });

  it("confirms qualification then surfaces a consumed 409", async () => {
    startPdfEvalExam.mockRejectedValue(new Error("qualification_consumed"));
    renderBoard(<EvaluationExamBoard auth={AUTH} onOpenCase={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Run qualification exam" }));
    expect(screen.getByRole("dialog", { name: "Start the one qualification exam?" })).toBeInTheDocument();
    startPdfEvalExam.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(startPdfEvalExam).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Run qualification exam" }));
    fireEvent.click(screen.getByRole("button", { name: "Start qualification" }));
    expect(await screen.findByText(/one qualification attempt/)).toBeInTheDocument();
    expect(startPdfEvalExam).toHaveBeenCalledWith(
      AUTH,
      expect.objectContaining({ split: "qualification" }),
    );
    expect(screen.queryByText(/gates_pass/i)).toBeNull();
  });

  it("keeps the official report when the current exam fails", async () => {
    fetchPdfEvalLatestReport.mockResolvedValue(passReport());
    writeEvalExamPointer({ examRunId: "exam-fail", split: "development" });
    fetchPdfEvalExam.mockResolvedValue(
      examStatus({
        exam_run_id: "exam-fail",
        status: "failed",
        completed_case_count: 1,
      }),
    );
    renderBoard(<EvaluationExamBoard auth={AUTH} onOpenCase={vi.fn()} />);
    expect(
      await screen.findByText(
        "All required gold chunks in the production Hybrid top 10: 4 of 4 (100%)",
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("The failed exam did not replace the official report."),
    ).toBeInTheDocument();
  });

  it("opens a scored case without rendering private case text", async () => {
    const onOpenCase = vi.fn();
    fetchPdfEvalLatestReport.mockResolvedValue(passReport());
    renderBoard(<EvaluationExamBoard auth={AUTH} onOpenCase={onOpenCase} />);
    fireEvent.click(await screen.findByRole("button", { name: /Open case 2 · miss/ }));
    expect(onOpenCase).toHaveBeenCalledWith("case-2");
    expect(screen.queryByText(/<img/)).toBeNull();
  });

  it("cancels an active exam", async () => {
    writeEvalExamPointer({ examRunId: "exam-1", split: "development" });
    fetchPdfEvalExam.mockResolvedValue(
      examStatus({ status: "running", completed_case_count: 1 }),
    );
    renderBoard(<EvaluationExamBoard auth={AUTH} onOpenCase={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel exam" }));
    await waitFor(() => {
      expect(cancelPdfEvalExam).toHaveBeenCalledWith(AUTH, "exam-1");
    });
  });
});
