// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { SessionProvider } from "../../lib/auth/session-provider";
import type { PdfEvalCaseDetail, PdfEvalCaseSummary, PdfEvalPassage } from "../../lib/types";
import { EvaluationPanel } from "./evaluation-panel";

const fetchPdfEvalStatus = vi.fn();
const listPdfEvalCases = vi.fn();
const fetchPdfEvalCase = vi.fn();
const patchPdfEvalCase = vi.fn();
const setPdfEvalApproval = vi.fn();
const listPdfEvalPassages = vi.fn();
const comparePdfEvalRun = vi.fn();
const replacePdfEvalGold = vi.fn();
const deletePdfEvalCase = vi.fn();
const regeneratePdfEvalDrafts = vi.fn();
const listDocuments = vi.fn();
const fetchDocument = vi.fn();
const fetchPdfEvalLatestReport = vi.fn();
const fetchPdfEvalExam = vi.fn();
const startPdfEvalExam = vi.fn();
const cancelPdfEvalExam = vi.fn();
const listPdfEvalExamCases = vi.fn();
const send = vi.fn(async (text: string) => {
  sentMessages.push(text);
  return true;
});
const sentMessages: string[] = [];

const DOC = "22222222-2222-4222-8222-222222222222";
const CITED = "33333333-3333-4333-8333-333333333333";
const OTHER = "44444444-4444-4444-8444-444444444444";

vi.mock("../../lib/auth/browser", () => ({
  createBrowserSupabase: () => ({
    auth: {
      getSession: vi.fn(async () => ({
        data: {
          session: { access_token: "jwt-token", user: { email: "a@b.test" } },
        },
      })),
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
      signOut: vi.fn(),
    },
  }),
}));

vi.mock("../../lib/env", () => ({
  publicSupabaseConfig: () => ({
    url: "http://127.0.0.1:54321",
    anonKey: "anon",
  }),
  apiBaseUrl: () => "http://127.0.0.1:8000",
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    fetchPdfEvalStatus: (...args: unknown[]) => fetchPdfEvalStatus(...args),
    listPdfEvalCases: (...args: unknown[]) => listPdfEvalCases(...args),
    fetchPdfEvalCase: (...args: unknown[]) => fetchPdfEvalCase(...args),
    patchPdfEvalCase: (...args: unknown[]) => patchPdfEvalCase(...args),
    setPdfEvalApproval: (...args: unknown[]) => setPdfEvalApproval(...args),
    listPdfEvalPassages: (...args: unknown[]) => listPdfEvalPassages(...args),
    comparePdfEvalRun: (...args: unknown[]) => comparePdfEvalRun(...args),
    replacePdfEvalGold: (...args: unknown[]) => replacePdfEvalGold(...args),
    deletePdfEvalCase: (...args: unknown[]) => deletePdfEvalCase(...args),
    regeneratePdfEvalDrafts: (...args: unknown[]) => regeneratePdfEvalDrafts(...args),
    listDocuments: (...args: unknown[]) => listDocuments(...args),
    fetchDocument: (...args: unknown[]) => fetchDocument(...args),
    fetchPdfEvalLatestReport: (...args: unknown[]) => fetchPdfEvalLatestReport(...args),
    fetchPdfEvalExam: (...args: unknown[]) => fetchPdfEvalExam(...args),
    startPdfEvalExam: (...args: unknown[]) => startPdfEvalExam(...args),
    cancelPdfEvalExam: (...args: unknown[]) => cancelPdfEvalExam(...args),
    listPdfEvalExamCases: (...args: unknown[]) => listPdfEvalExamCases(...args),
  };
});

vi.mock("../chat/hooks/use-chat-queries", () => ({
  useChatQueries: () => ({
    meta: {
      api_version: "1",
      sse_schema_version: "1",
      min_client_version: "0.1.0",
      pdf_eval_workspace: true,
    },
    metaPending: false,
    metaError: false,
    ready: {
      status: "ok",
      query_ready: true,
      detail: "ok",
      rate_limit_degraded: false,
      dependencies: [],
    },
  }),
}));

vi.mock("../chat/hooks/use-chat-run", () => ({
  useChatRun: () => ({
    chat: { terminal: null, runId: null, answerText: "" },
    sending: false,
    disconnected: false,
    reconnectAttempt: 0,
    send,
    resetRun: vi.fn(),
  }),
}));

afterEach(() => {
  cleanup();
  sentMessages.length = 0;
  sessionStorage.clear();
});

function summary(overrides: Partial<PdfEvalCaseSummary> = {}): PdfEvalCaseSummary {
  return {
    case_id: "case-hostile",
    split: "development",
    query_class: "<img src=x onerror=alert(1)>",
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

function detail(overrides: Partial<PdfEvalCaseDetail> = {}): PdfEvalCaseDetail {
  return {
    revision: "1",
    case_id: "case-hostile",
    split: "development",
    query_class: "<img src=x onerror=alert(1)>",
    human_approved: false,
    generated_only: true,
    reviewer: null,
    expected_refusal: false,
    expected_scope: "unscoped",
    chunk_ids: [CITED],
    page_numbers: [1],
    heading_paths: ["Chapter 1"],
    required_terms: ["Hybrid"],
    question: "What is stated about Hybrid?",
    expected_answer: "SECRET_EXPECTED_ANSWER",
    atomic_facts: ["Agents coordinate tools."],
    review_status: "draft",
    source_family_id: null,
    source_run_id: null,
    document_id: DOC,
    version_id: "11111111-1111-4111-8111-111111111111",
    gold: [
      {
        ordinal: 1,
        chunk_id: CITED,
        document_id: DOC,
        version_id: "11111111-1111-4111-8111-111111111111",
        page_number: 1,
        page_label: "1",
        section_path: ["Chapter 1"],
        stale: false,
      },
    ],
    gold_stale: false,
    reviewer_user_id: null,
    row_version: 1,
    ...overrides,
  };
}

function passage(chunkId: string, text: string, heading?: string): PdfEvalPassage {
  return {
    chunk_id: chunkId,
    document_id: DOC,
    version_id: "11111111-1111-4111-8111-111111111111",
    page_number: chunkId === OTHER ? 2 : 1,
    heading_path: [heading ?? (chunkId === OTHER ? "Appendix" : "Chapter 1")],
    raw_text: text,
  };
}

beforeEach(() => {
  fetchPdfEvalStatus.mockResolvedValue({
    enabled: true,
    case_count: 1,
    revision: null,
    version_id: "11111111-1111-4111-8111-111111111111",
    document_id: DOC,
    dataset_present: true,
    stale_gold_count: 0,
  });
  listPdfEvalCases.mockResolvedValue({
    revision: "",
    items: [summary()],
    next_case_id: null,
  });
  fetchPdfEvalCase.mockResolvedValue(detail());
  listPdfEvalPassages.mockResolvedValue({
    items: [
      passage(CITED, "Hybrid retrieval text"),
      passage(OTHER, "مرحبا <img src=x onerror=alert(1)> extra chunk"),
    ],
    next_chunk_id: null,
  });
  listDocuments.mockResolvedValue([
    {
      document_id: DOC,
      title: "Hybrid guide",
      visibility: "company",
      current_version_id: "11111111-1111-4111-8111-111111111111",
      visibility_generation: 1,
      created_at: null,
    },
  ]);
  fetchDocument.mockResolvedValue({
    ok: true,
    document: {
      document_id: DOC,
      title: "Hybrid guide",
      visibility: "company",
      current_version_id: "11111111-1111-4111-8111-111111111111",
      visibility_generation: 1,
      created_at: null,
    },
  });
  patchPdfEvalCase.mockResolvedValue({
    case_id: "case-hostile",
    row_version: 2,
    replayed: false,
  });
  replacePdfEvalGold.mockResolvedValue({
    case_id: "case-hostile",
    row_version: 2,
    replayed: false,
    gold_chunk_count: 1,
  });
  setPdfEvalApproval.mockResolvedValue({
    case_id: "case-hostile",
    row_version: 2,
    replayed: false,
  });
  deletePdfEvalCase.mockResolvedValue({
    case_id: "case-hostile",
    row_version: 1,
    replayed: false,
  });
  regeneratePdfEvalDrafts.mockResolvedValue({
    case_id: null,
    row_version: null,
    replayed: false,
    inserted_count: 2,
  });
  fetchPdfEvalLatestReport.mockResolvedValue({
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
  });
  fetchPdfEvalExam.mockResolvedValue({
    exam_run_id: "exam-1",
    split: "development",
    status: "queued",
    dataset_hash: "",
    case_count: 0,
    completed_case_count: 0,
    holdout_opened: false,
    candidate_fingerprint: null,
  });
  listPdfEvalExamCases.mockResolvedValue({
    exam_run_id: "exam-1",
    items: [],
    missed_count: 0,
  });
});

/**
 * Render the evaluation panel with session and query context.
 *
 * @param ui - Element.
 * @returns Render result.
 */
function renderSurface(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>{ui}</SessionProvider>
    </QueryClientProvider>,
  );
}

async function openReviewCases(): Promise<void> {
  fireEvent.click(await screen.findByRole("tab", { name: "Review cases" }));
}

describe("EvaluationPanel", () => {
  it("defaults to Overview and keeps exam results on a separate task view", async () => {
    renderSurface(<EvaluationPanel />);
    expect(await screen.findByRole("tab", { name: "Overview", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate review cases" })).toBeInTheDocument();
    expect(screen.getByLabelText("Draft cases")).toBeInTheDocument();
    expect(screen.getByLabelText("Draft cases")).toHaveTextContent("—");
    expect(screen.queryByRole("heading", { name: "Official Recall@10" })).toBeNull();
    expect(screen.queryByLabelText("Question")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Exam results" }));
    expect(await screen.findByRole("heading", { name: "Official Recall@10" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Run development exam" }),
    ).toBeInTheDocument();
  });

  it("moves between task views with arrow keys", async () => {
    const user = userEvent.setup();
    renderSurface(<EvaluationPanel />);
    const overview = await screen.findByRole("tab", { name: "Overview" });
    overview.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Review cases" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Review cases" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Exam results" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveFocus();
  });

  it("renders hostile case labels as text and keeps AI-test expected answers collapsed", async () => {
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(await screen.findByLabelText("Expected answer")).toHaveValue(
      "SECRET_EXPECTED_ANSWER",
    );
    expect(screen.getByRole("button", { name: "Reveal expected answer" })).toBeDisabled();
    fireEvent.click(await screen.findByRole("button", { name: "Run test" }));
    await waitFor(() => {
      expect(sentMessages).toEqual(["What is stated about Hybrid?"]);
    });
    expect(sentMessages[0]).not.toContain("SECRET_EXPECTED_ANSWER");
    expect(screen.getByRole("button", { name: "Compare cited sources" })).toBeDisabled();
    expect(screen.queryByRole("heading", { name: "Official Recall@10" })).toBeNull();
    expect(
      screen.getByText(/It is not official Recall@10/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Question")).toHaveValue("What is stated about Hybrid?");
    const queue = screen.getByRole("navigation", { name: "Evaluation cases" });
    expect(within(queue).queryByText("What is stated about Hybrid?")).toBeNull();
    expect(within(queue).queryByText("SECRET_EXPECTED_ANSWER")).toBeNull();
  });

  it("hides Run for holdout cases", async () => {
    fetchPdfEvalCase.mockResolvedValue(detail({ case_id: "case-holdout", split: "holdout" }));
    listPdfEvalCases.mockResolvedValue({
      revision: "",
      items: [summary({ case_id: "case-holdout", split: "holdout" })],
      next_case_id: null,
    });
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    expect(await screen.findByText("Holdout cases cannot run from this page.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run test" })).toBeNull();
  });

  it("gates the workspace on a real 403", async () => {
    fetchPdfEvalStatus.mockRejectedValue(new Error("forbidden"));
    renderSurface(<EvaluationPanel />);
    expect(await screen.findByText("You don’t have access.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Question")).toBeNull();
  });

  it("shows empty, loading, and list errors", async () => {
    listPdfEvalCases.mockResolvedValue({ revision: "", items: [], next_case_id: null });
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    expect(await screen.findByText("No cases match these filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
    cleanup();
    listPdfEvalCases.mockRejectedValue(new Error("request_rejected"));
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    expect(await screen.findByText("Cases could not load.")).toBeInTheDocument();
  });

  it("requests the first 20 cases and paginates with Load more", async () => {
    const first = Array.from({ length: 20 }, (_, index) =>
      summary({
        case_id: `case-${String(index)}`,
        query_class: `factual_definition_${String(index)}`,
      }),
    );
    listPdfEvalCases.mockImplementation(
      (_auth: unknown, _fetch: unknown, query: { after?: string | null } = {}) => {
        if (query.after) {
          return Promise.resolve({
            revision: "",
            items: [summary({ case_id: "case-20", query_class: "factual_definition" })],
            next_case_id: null,
          });
        }
        return Promise.resolve({
          revision: "",
          items: first,
          next_case_id: "case-19",
        });
      },
    );
    fetchPdfEvalCase.mockResolvedValue(detail({ case_id: "case-0" }));
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    expect(await screen.findByRole("button", { name: "Load more" })).toBeInTheDocument();
    await waitFor(() => {
      const query = listPdfEvalCases.mock.calls[0]?.[2] as { limit?: number };
      expect(query.limit).toBe(20);
    });
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Factual definition")).toBeInTheDocument();
    await waitFor(() => {
      const loadQuery = listPdfEvalCases.mock.calls.find(
        (call) => (call[2] as { after?: string } | undefined)?.after === "case-19",
      );
      expect(loadQuery).toBeDefined();
    });
  });

  it("sends review_status when the Review filter changes", async () => {
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    await screen.findByRole("button", { name: "Run test" });
    fireEvent.change(screen.getByLabelText("Review status"), { target: { value: "approved" } });
    await waitFor(() => {
      const filtered = listPdfEvalCases.mock.calls.some((call) => {
        const query = call[2] as { review_status?: string } | undefined;
        return query?.review_status === "approved";
      });
      expect(filtered).toBe(true);
    });
  });

  it("lets the keyboard pick a non-citation gold chunk and saves 0–3 IDs", async () => {
    const user = userEvent.setup();
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    const extra = await screen.findByRole("checkbox", {
      name: /Appendix/,
    });
    extra.focus();
    await user.keyboard(" ");
    fireEvent.click(screen.getByRole("button", { name: "Save source passages" }));
    await waitFor(() => {
      expect(replacePdfEvalGold).toHaveBeenCalledWith(
        expect.anything(),
        "case-hostile",
        1,
        expect.arrayContaining([CITED, OTHER]),
      );
    });
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText(/مرحبا/)).toBeInTheDocument();
  });

  it("blocks Approve when gold is stale", async () => {
    fetchPdfEvalCase.mockResolvedValue(detail({ gold_stale: true }));
    listPdfEvalCases.mockResolvedValue({
      revision: "",
      items: [summary({ gold_stale: true })],
      next_case_id: null,
    });
    fetchPdfEvalStatus.mockResolvedValue({
      enabled: true,
      case_count: 1,
      revision: null,
      version_id: null,
      document_id: DOC,
      dataset_present: true,
      stale_gold_count: 1,
    });
    renderSurface(<EvaluationPanel />);
    expect(
      await screen.findByText(
        "1 cases have stale sources. Remap those locators before approval or exam.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Repair stale sources first" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review stale cases" }));
    expect(
      await screen.findByText(
        "This document version changed. Remap required sources from current passages and reapprove.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve case" })).toBeDisabled();
    expect(
      screen.getByText(
        "Remap required sources from current passages before approval. Stale sources cannot be approved.",
      ),
    ).toBeInTheDocument();
  });

  it("reloads the case after a stale row_version conflict", async () => {
    patchPdfEvalCase.mockRejectedValue(new Error("stale_row_version"));
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    fireEvent.change(await screen.findByLabelText("Question"), {
      target: { value: "Changed question?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(
      await screen.findByText("This case changed. Reloaded the latest version."),
    ).toBeInTheDocument();
    expect(patchPdfEvalCase.mock.calls[0]?.[2]).toBe(1);
    expect(patchPdfEvalCase.mock.calls[0]?.[3]).not.toHaveProperty("expected_revision");
  });

  it("returns focus to Delete after the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    const trigger = await screen.findByRole("button", { name: "Delete" });
    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "Delete this quiz case?" });
    expect(within(dialog).getByText(/development/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Delete" })).toHaveFocus();
    });
  });

  it("shows regenerate pending, success, 409, and error states", async () => {
    let settle: ((value: unknown) => void) | undefined;
    const pending = new Promise((resolve) => {
      settle = resolve;
    });
    regeneratePdfEvalDrafts.mockImplementation(() => pending);
    renderSurface(<EvaluationPanel />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Generate review cases" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate review cases" }));
    expect(await screen.findByRole("button", { name: "Regenerating…" })).toBeDisabled();
    settle?.({
      case_id: null,
      row_version: null,
      replayed: false,
      inserted_count: 2,
    });
    expect(
      await screen.findByText(
        "Created 2 draft cases. Review them before running an exam.",
      ),
    ).toBeInTheDocument();

    regeneratePdfEvalDrafts.mockReset();
    regeneratePdfEvalDrafts.mockRejectedValueOnce(new Error("capacity_exceeded"));
    fireEvent.click(screen.getByRole("button", { name: "Generate review cases" }));
    expect(
      await screen.findByText(
        "The workspace is at capacity. Delete cases before regenerating.",
      ),
    ).toBeInTheDocument();

    regeneratePdfEvalDrafts.mockRejectedValueOnce(new Error("request_rejected"));
    fireEvent.click(screen.getByRole("button", { name: "Generate review cases" }));
    expect(await screen.findByText("Drafts could not be regenerated.")).toBeInTheDocument();
  });

  it("offers onboarding when the workspace has zero cases", async () => {
    fetchPdfEvalStatus.mockResolvedValue({
      enabled: true,
      case_count: 0,
      revision: null,
      version_id: null,
      document_id: null,
      dataset_present: false,
      stale_gold_count: 0,
      draft_count: 0,
      approved_count: 0,
      remaining_capacity: 60,
    });
    listPdfEvalCases.mockResolvedValue({ revision: "", items: [], next_case_id: null });
    renderSurface(<EvaluationPanel />);
    expect(await screen.findByText("Create your first review set")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate review cases" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Review cases" }));
    expect(await screen.findByText("No review cases yet")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Go to Overview" }));
    expect(await screen.findByText("Create your first review set")).toBeInTheDocument();
  });

  it("guides draft review without starting an exam", async () => {
    fetchPdfEvalStatus.mockResolvedValue({
      enabled: true,
      case_count: 1,
      revision: null,
      version_id: "11111111-1111-4111-8111-111111111111",
      document_id: DOC,
      dataset_present: true,
      stale_gold_count: 0,
      draft_count: 1,
      approved_count: 0,
      remaining_capacity: 59,
    });
    renderSurface(<EvaluationPanel />);
    expect(await screen.findByText("Cases are waiting for review")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review next case" }));
    expect(await screen.findByLabelText("Question")).toBeInTheDocument();
    expect(startPdfEvalExam).not.toHaveBeenCalled();
  });

  it("opens exam results from ready guidance without starting an exam", async () => {
    fetchPdfEvalStatus.mockResolvedValue({
      enabled: true,
      case_count: 4,
      revision: null,
      version_id: "11111111-1111-4111-8111-111111111111",
      document_id: DOC,
      dataset_present: true,
      stale_gold_count: 0,
      draft_count: 0,
      approved_count: 4,
      remaining_capacity: 56,
    });
    renderSurface(<EvaluationPanel />);
    expect(await screen.findByText("The review set is ready")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View exam results" }));
    expect(await screen.findByRole("heading", { name: "Official Recall@10" })).toBeInTheDocument();
    expect(startPdfEvalExam).not.toHaveBeenCalled();
  });

  it("blocks Approve while case details or source selection are unsaved", async () => {
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    expect(await screen.findByRole("button", { name: "Approve case" })).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Question"), {
      target: { value: "Unsaved question?" },
    });
    expect(screen.getByRole("button", { name: "Approve case" })).toBeDisabled();
    expect(screen.getByText("Save case details before approval.")).toBeInTheDocument();
    expect(screen.getByText("Unsaved case details")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Question"), {
      target: { value: "What is stated about Hybrid?" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Appendix/ }));
    expect(screen.getByRole("button", { name: "Approve case" })).toBeDisabled();
    expect(screen.getByText("Save source changes before approval.")).toBeInTheDocument();
    expect(screen.getByText("Unsaved source changes")).toBeInTheDocument();
  });

  it("blocks Approve when no required sources are saved", async () => {
    fetchPdfEvalCase.mockResolvedValue(detail({ chunk_ids: [], gold: [] }));
    listPdfEvalCases.mockResolvedValue({
      revision: "",
      items: [summary({ gold_chunk_count: 0 })],
      next_case_id: null,
    });
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    expect(await screen.findByRole("button", { name: "Approve case" })).toBeDisabled();
    expect(
      screen.getByText("Select 1–3 current source passages before approval."),
    ).toBeInTheDocument();
  });

  it("clears dataset, review, and source filters together", async () => {
    listPdfEvalCases.mockImplementation(
      (_auth: unknown, _fetch: unknown, query: { review_status?: string } = {}) => {
        if (query.review_status === "approved") {
          return Promise.resolve({ revision: "", items: [], next_case_id: null });
        }
        return Promise.resolve({
          revision: "",
          items: [summary()],
          next_case_id: null,
        });
      },
    );
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    await screen.findByRole("button", { name: "Run test" });
    fireEvent.change(screen.getByLabelText("Review status"), { target: { value: "approved" } });
    expect(await screen.findByText("No cases match these filters")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(
      (await screen.findAllByText("<img src=x onerror=alert(1)>")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByLabelText("Review status")).toHaveValue("all");
    expect(screen.getByLabelText("Dataset")).toHaveValue("all");
    expect(screen.getByLabelText("Source status")).toHaveValue("all");
  });

  it("shows review and source status labels without private queue text", async () => {
    listPdfEvalCases.mockResolvedValue({
      revision: "",
      items: [
        summary({ review_status: "approved", human_approved: true, gold_chunk_count: 2 }),
        summary({
          case_id: "case-rejected",
          review_status: "rejected",
          query_class: "exact_acronym",
          gold_stale: true,
          gold_chunk_count: 1,
        }),
      ],
      next_case_id: null,
    });
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    const queue = await screen.findByRole("navigation", { name: "Evaluation cases" });
    expect(within(queue).getByText("Approved")).toBeInTheDocument();
    expect(within(queue).getByText("Rejected")).toBeInTheDocument();
    expect(within(queue).getByText("Exact acronym")).toBeInTheDocument();
    expect(within(queue).getByText("Sources current")).toBeInTheDocument();
    expect(within(queue).getByText("Sources stale")).toBeInTheDocument();
    expect(within(queue).getByText("2 sources")).toBeInTheDocument();
    expect(within(queue).queryByText("SECRET_EXPECTED_ANSWER")).toBeNull();
    expect(within(queue).queryByText("What is stated about Hybrid?")).toBeNull();
  });

  it("blocks a fourth required source and keeps 0–3 selection", async () => {
    const third = "55555555-5555-4555-8555-555555555555";
    const fourth = "66666666-6666-4666-8666-666666666666";
    listPdfEvalPassages.mockResolvedValue({
      items: [
        passage(CITED, "Hybrid retrieval text"),
        passage(OTHER, "مرحبا extra chunk"),
        passage(third, "Third authorized passage", "Third heading"),
        passage(fourth, "Fourth authorized passage", "Fourth heading"),
      ],
      next_chunk_id: null,
    });
    fetchPdfEvalCase.mockResolvedValue(detail({ chunk_ids: [], gold: [] }));
    renderSurface(<EvaluationPanel />);
    await openReviewCases();
    const first = await screen.findByRole("checkbox", { name: /Chapter 1/ });
    const second = screen.getByRole("checkbox", { name: /Appendix/ });
    const extra = screen.getByRole("checkbox", { name: /Third heading/ });
    const blocked = screen.getByRole("checkbox", { name: /Fourth heading/ });
    fireEvent.click(first);
    fireEvent.click(second);
    fireEvent.click(extra);
    expect(first).toBeChecked();
    expect(second).toBeChecked();
    expect(extra).toBeChecked();
    expect(blocked).toBeDisabled();
    expect(screen.getByText("3 of 3 selected")).toBeInTheDocument();
    expect(
      screen.getByText("Remove a selected passage before choosing another."),
    ).toBeInTheDocument();
  });

  it("shows a labelled loading spinner and a generic workspace error", async () => {
    fetchPdfEvalStatus.mockImplementation(() => new Promise(() => undefined));
    renderSurface(<EvaluationPanel />);
    expect(await screen.findByRole("status", { name: "Loading evaluation workspace" })).toBeInTheDocument();
    cleanup();
    fetchPdfEvalStatus.mockRejectedValue(new Error("request_rejected"));
    renderSurface(<EvaluationPanel />);
    expect(await screen.findByText("Evaluation is unavailable.")).toBeInTheDocument();
  });
});

