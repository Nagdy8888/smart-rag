// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { SessionProvider } from "../../lib/auth/session-provider";
import { EvaluationPanel } from "./evaluation-panel";

const fetchPdfEvalStatus = vi.fn();
const listPdfEvalCases = vi.fn();
const fetchPdfEvalCase = vi.fn();
const patchPdfEvalCase = vi.fn();
const setPdfEvalApproval = vi.fn();
const listPdfEvalPassages = vi.fn();
const comparePdfEvalRun = vi.fn();
const send = vi.fn(async (text: string) => {
  sentMessages.push(text);
  return true;
});
const sentMessages: string[] = [];

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
});

beforeEach(() => {
  fetchPdfEvalStatus.mockResolvedValue({
    enabled: true,
    case_count: 1,
    revision: "aa".repeat(32),
    version_id: "11111111-1111-4111-8111-111111111111",
    document_id: "22222222-2222-4222-8222-222222222222",
    dataset_present: true,
  });
  listPdfEvalCases.mockResolvedValue({
    revision: "aa".repeat(32),
    items: [
      {
        case_id: "case-hostile",
        split: "development",
        query_class: "<img src=x onerror=alert(1)>",
        human_approved: false,
        generated_only: true,
        reviewer: null,
        expected_refusal: false,
        gold_chunk_count: 1,
      },
    ],
    next_case_id: null,
  });
  fetchPdfEvalCase.mockResolvedValue({
    revision: "aa".repeat(32),
    case_id: "case-hostile",
    split: "development",
    query_class: "<img src=x onerror=alert(1)>",
    human_approved: false,
    generated_only: true,
    reviewer: null,
    expected_refusal: false,
    expected_scope: "unscoped",
    chunk_ids: ["33333333-3333-4333-8333-333333333333"],
    page_numbers: [1],
    heading_paths: ["Chapter 1"],
    required_terms: ["Hybrid"],
    question: "What is stated about Hybrid?",
    expected_answer: "SECRET_EXPECTED_ANSWER",
    atomic_facts: ["Agents coordinate tools."],
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

describe("EvaluationPanel", () => {
  it("renders hostile case labels as text and keeps expected answers collapsed", async () => {
    renderSurface(<EvaluationPanel />);
    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.queryByText("SECRET_EXPECTED_ANSWER")).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "Run" }));
    await waitFor(() => {
      expect(sentMessages).toEqual(["What is stated about Hybrid?"]);
    });
    expect(sentMessages[0]).not.toContain("SECRET_EXPECTED_ANSWER");
    expect(screen.getByRole("button", { name: "Compare citations" })).toBeDisabled();
  });

  it("hides Run for holdout cases", async () => {
    fetchPdfEvalCase.mockResolvedValue({
      revision: "aa".repeat(32),
      case_id: "case-holdout",
      split: "holdout",
      query_class: "factual_definition",
      human_approved: false,
      generated_only: true,
      reviewer: null,
      expected_refusal: false,
      expected_scope: "unscoped",
      chunk_ids: ["33333333-3333-4333-8333-333333333333"],
      page_numbers: [1],
      heading_paths: ["Chapter 1"],
      required_terms: ["Hybrid"],
      question: "Holdout question",
      expected_answer: "secret",
      atomic_facts: [],
    });
    listPdfEvalCases.mockResolvedValue({
      revision: "aa".repeat(32),
      items: [
        {
          case_id: "case-holdout",
          split: "holdout",
          query_class: "factual_definition",
          human_approved: false,
          generated_only: true,
          reviewer: null,
          expected_refusal: false,
          gold_chunk_count: 1,
        },
      ],
      next_case_id: null,
    });
    renderSurface(<EvaluationPanel />);
    expect(await screen.findByText("Holdout cases cannot run from this page.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run" })).toBeNull();
  });
});
